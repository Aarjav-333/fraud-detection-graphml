"""Regression tests for the code-review findings, one (or two) per fix."""
import io
import time
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from conftest import SessionLocal
from test_email import confirm, delivery
from test_fraud_review import review
from test_migrations import MIGRATIONS, OLD_SCHEMA, _columns
from test_notifications import flagged, notifications_for, pay  # noqa: F401  (flagged is a fixture)
from app.config import Settings, settings
from app.models.account import Account
from app.models.alert import Alert
from app.models.email_delivery import EmailDelivery
from app.models.transaction import Transaction
from app.models.user import User


def upload(client, headers, csv_text):
    return client.post("/api/transactions/upload", headers=headers,
                       files={"file": ("t.csv", io.BytesIO(csv_text.encode()), "text/csv")}).json()


# 1. a concurrent alert-number collision must not drop the notification
def test_alert_number_collision_still_notifies(client, users, db, flagged, monkeypatch):
    from app.services import notifications as svc
    sender, receiver = flagged
    pay(client, users["analyst"], sender, receiver, amount=100)   # an alert number in use
    real, calls = svc.next_alert_num, []

    def taken_first(session):
        calls.append(1)
        return real(session) - 1 if len(calls) == 1 else real(session)   # the newest alert already has it

    monkeypatch.setattr(svc, "next_alert_num", taken_first)
    txn = pay(client, users["analyst"], sender, receiver, amount=200).json()["txn_uid"]
    notes = notifications_for(db, txn)
    assert len(calls) == 2 and len(notes) == 1
    assert db.query(Alert).filter_by(alert_uid=notes[0].alert_uid).one().transaction_uid == txn


# 2. a cleared (or re-confirmed) account never gets the old "flagged" email
def test_cleared_account_never_gets_the_flagged_email(client, users, db, smtp, make_account, monkeypatch):
    from app.services import mailer
    uid = make_account()
    monkeypatch.setattr(settings, "SMTP_HOST", "")            # the email fails at first: not configured
    confirm(client, users["analyst"], uid)
    d = delivery(db, uid)
    assert d.status == "failed"
    review(client, users["analyst2"], uid, "clear", note="False positive: payroll account")
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")   # mail works again

    res = client.post(f"/api/accounts/{uid}/emails/{d.id}/retry", headers=users["analyst"])
    assert res.status_code == 409 and "no longer flagged" in res.json()["detail"]
    d.status = "pending"                                       # as if it was still queued when cleared
    db.commit()
    mailer.deliver(d.id)
    d = delivery(db, uid)
    assert d.status == "skipped" and "no longer flagged" in d.last_error
    assert smtp.messages == []


def test_old_email_not_sent_after_reconfirmation(client, users, db, smtp, make_account, monkeypatch):
    uid = make_account()
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    confirm(client, users["analyst"], uid)
    old = db.query(EmailDelivery).filter_by(account_uid=uid).one()
    review(client, users["analyst"], uid, "clear", note="Mistake")
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    confirm(client, users["analyst"], uid)                    # confirmed again: its own email, sent
    res = client.post(f"/api/accounts/{uid}/emails/{old.id}/retry", headers=users["analyst"])
    assert res.status_code == 409 and "later review decision" in res.json()["detail"]
    assert len(smtp.messages) == 1


# 3. an Idempotency-Key replay must match the original request
def test_reused_key_with_different_details_is_rejected(client, users, db, make_account):
    a, b = make_account(), make_account()
    key = str(uuid.uuid4())
    first = pay(client, users["analyst"], a, b, amount=500, key=key)
    changed = pay(client, users["analyst"], a, b, amount=5000, key=key)
    same = pay(client, users["analyst"], a, b, amount=500, key=key)
    assert (first.status_code, changed.status_code, same.status_code) == (201, 422, 200)
    assert first.json()["txn_uid"] in changed.json()["detail"]
    assert same.json()["txn_uid"] == first.json()["txn_uid"]
    assert db.query(Transaction).filter_by(sender_uid=a).count() == 1


# 4. numeric CSV keys stay text when the column has a blank
def test_numeric_csv_keys_stay_text(client, users, db, make_account):
    a, b = make_account(), make_account()
    base = int(time.time() * 1000) % 10**9
    header = "sender_uid,receiver_uid,amount,idempotency_key\n"
    rows = f"{a},{b},10,{base}\n{a},{b},11,{base + 1}\n"
    first = upload(client, users["analyst"], header + rows)
    second = upload(client, users["analyst"], header + rows + f"{a},{b},12,\n")
    assert (first["inserted"], second["inserted"], second["skipped"]) == (2, 1, 2)
    keys = {k for (k,) in db.query(Transaction.idempotency_key).filter_by(sender_uid=a)}
    assert keys == {str(base), str(base + 1), None}


# 5. an unrecognised SMTP_SECURITY is refused instead of sending in clear text
def test_smtp_security_must_be_known():
    assert Settings(_env_file=None, SMTP_SECURITY=" STARTTLS ").SMTP_SECURITY == "starttls"
    with pytest.raises(ValidationError, match="SMTP_SECURITY"):
        Settings(_env_file=None, SMTP_SECURITY="tls")


# 6. a concurrent status change is reported, not overwritten with a wrong history
def test_concurrent_change_is_not_overwritten(client, users, make_account):
    from app.services.fraud_review import ReviewError, change_review_status
    uid = make_account()
    stale = SessionLocal()
    a_view = stale.query(Account).filter_by(account_uid=uid).one()   # analyst A's view: not under review
    review(client, users["analyst2"], uid, "under_review", note="B is on it")
    analyst = stale.query(User).filter_by(username="t_analyst").one()
    assert a_view.review_status is None                                # A still sees the old status
    try:
        with pytest.raises(ReviewError, match="Another analyst changed this account to Under Review"):
            change_review_status(stale, uid, "confirm_fraud", analyst)
    finally:
        stale.close()
    detail = client.get(f"/api/accounts/{uid}/investigation", headers=users["analyst"]).json()
    assert detail["account"]["review_status"] == "Under Review"
    assert [(e["from_status"], e["to_status"]) for e in detail["status_history"]] == [(None, "Under Review")]


# 7. more keys than SQLite allows in one IN list (32,766)
def test_large_csv_upload_with_keys(client, users, make_account):
    a, b = make_account(), make_account()
    n = 33_000
    prefix = uuid.uuid4().hex[:8]
    csv_text = "sender_uid,receiver_uid,amount,idempotency_key\n" + "".join(f"{a},{b},1,{prefix}-{i}\n" for i in range(n))
    assert upload(client, users["analyst"], csv_text)["inserted"] == n
    again = upload(client, users["analyst"], csv_text)
    assert (again["inserted"], again["skipped"]) == (0, n)


# 8. a column added by another process starting at the same moment
def test_column_added_by_another_process(tmp_path: Path, monkeypatch):
    import app.migrations as migrations
    engine = create_engine(f"sqlite:///{tmp_path.as_posix()}/race.db")
    with engine.begin() as conn:
        for statement in OLD_SCHEMA:
            conn.execute(text(statement))
        conn.execute(text("ALTER TABLE accounts ADD COLUMN review_status VARCHAR"))   # the other process's work

    class StaleInspector:   # what we saw just before it was added
        def get_columns(self, table):
            return []

    monkeypatch.setattr(migrations, "inspect", lambda conn: StaleInspector())
    assert migrations.run_migrations(engine) == [version for version, _ in MIGRATIONS]
    monkeypatch.undo()
    assert {"review_status", "fraud_confirmed_at"} <= _columns(engine, "accounts")


# 9. after an upload only rows from confirmed-fraud senders are loaded for notifications
def test_csv_upload_only_rechecks_flagged_senders(client, users, flagged, make_account, monkeypatch):
    import app.api.transactions as api
    sender, receiver = flagged
    normal = make_account()
    seen = []
    real = api.on_transactions_recorded
    monkeypatch.setattr(api, "on_transactions_recorded",
                        lambda session, txns: seen.extend((t.sender_uid, t.amount) for t in txns) or real(session, txns))
    result = upload(client, users["analyst"],
                    f"sender_uid,receiver_uid,amount\n{normal},{receiver},10\n{sender},{receiver},20\n{normal},{sender},30\n")
    assert result["inserted"] == 3
    assert seen == [(sender, 20)]

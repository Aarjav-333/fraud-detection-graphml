"""Test cases 3 (email delivery), 6 (no duplicate emails) and 7 (email failures)."""
import pytest

from app.models.account import Account
from app.models.email_delivery import EmailDelivery


def confirm(client, headers, uid, txn=None):
    return client.post(f"/api/accounts/{uid}/review",
                       json={"action": "confirm_fraud", "transaction_uid": txn}, headers=headers)


def delivery(db, uid):
    db.expire_all()
    return db.query(EmailDelivery).filter_by(account_uid=uid).one()


def test_confirmation_emails_the_account_holder(client, users, db, smtp, make_account, make_txn):
    uid = make_account(email="ravi.k@fraudgraph-test-inbox.com", name="Ravi Kumar")
    txn = make_txn(uid, make_account(), amount=125000)

    res = confirm(client, users["analyst"], uid, txn)
    assert res.status_code == 200

    assert len(smtp.messages) == 1
    sent = smtp.messages[0]
    message = sent["message"]
    assert sent["to"] == ["ravi.k@fraudgraph-test-inbox.com"]
    assert message["Subject"] == "Important Security Alert – Your Account Has Been Flagged"
    text = message.get_body(preferencelist=("plain",)).get_content()
    page = message.get_body(preferencelist=("html",)).get_content()
    for body in (text, page):
        assert "Dear Ravi Kumar," in body
        assert "XXXX" + uid[-4:] in body           # masked account reference
        assert uid not in body                     # never the full account id
        assert txn in body and "₹1,25,000" in body
        assert "Flagged for Fraudulent Activity" in body
        assert "reviewed and confirmed by our fraud analysis team" in body
        assert "score" not in body.lower()         # no model information
    d = delivery(db, uid)
    assert (d.status, d.attempts, d.recipient_masked) == ("sent", 1, "r***@fraudgraph-test-inbox.com")
    assert d.sent_at is not None and d.requested_by == "t_analyst"

    detail = client.get(f"/api/accounts/{uid}/investigation", headers=users["analyst"]).json()
    assert detail["emails"][0]["status"] == "sent"


def test_no_second_email_for_a_repeated_confirmation(client, users, db, smtp, make_account):
    uid = make_account()
    confirm(client, users["analyst"], uid)
    confirm(client, users["analyst"], uid)
    confirm(client, users["admin"], uid)
    assert len(smtp.messages) == 1
    assert db.query(EmailDelivery).filter_by(account_uid=uid).count() == 1


def test_mail_server_down_keeps_the_confirmation(client, users, db, smtp_down, make_account, monkeypatch):
    uid = make_account()
    res = confirm(client, users["analyst"], uid)
    assert res.status_code == 200 and res.json()["account"]["fraud_status"] == "Confirmed Fraud"
    d = delivery(db, uid)
    assert d.status == "failed" and d.attempts == 3 and d.last_error   # retried, then gave up
    db.expire_all()
    assert db.query(Account).filter_by(account_uid=uid).one().review_status == "Confirmed Fraud"

    # the server comes back: retrying sends it
    from aiosmtpd.controller import Controller
    from conftest import _Inbox
    inbox = _Inbox()
    controller = Controller(inbox, hostname="127.0.0.1", port=smtp_down)
    controller.start()
    try:
        res = client.post(f"/api/accounts/{uid}/emails/{d.id}/retry", headers=users["analyst"])
        assert res.status_code == 200
        assert len(inbox.messages) == 1
        assert delivery(db, uid).status == "sent"
        again = client.post(f"/api/accounts/{uid}/emails/{d.id}/retry", headers=users["analyst"])
        assert again.status_code == 409   # already sent: never twice
    finally:
        controller.stop()


def test_email_not_configured(client, users, db, make_account):
    uid = make_account()
    res = confirm(client, users["analyst"], uid)
    assert res.status_code == 200 and res.json()["account"]["fraud_status"] == "Confirmed Fraud"
    d = delivery(db, uid)
    assert d.status == "failed" and "not configured" in d.last_error


@pytest.mark.parametrize("email", ["someone@example.com", "", "not-an-address"])
def test_no_usable_address_is_skipped(client, users, db, smtp, make_account, email):
    uid = make_account(email=email)
    assert confirm(client, users["analyst"], uid).status_code == 200
    d = delivery(db, uid)
    assert d.status == "skipped" and d.last_error and not smtp.messages

    # once the holder's address is corrected, the email can be retried
    client.put(f"/api/accounts/{uid}", json={"email": "fixed@fraudgraph-test-inbox.com"}, headers=users["analyst"])
    assert client.post(f"/api/accounts/{uid}/emails/{d.id}/retry", headers=users["analyst"]).status_code == 200
    assert delivery(db, uid).status == "sent" and smtp.messages[0]["to"] == ["fixed@fraudgraph-test-inbox.com"]


def test_under_review_sends_nothing(client, users, db, smtp, make_account):
    uid = make_account()
    client.post(f"/api/accounts/{uid}/review", json={"action": "under_review"}, headers=users["analyst"])
    assert not smtp.messages and db.query(EmailDelivery).filter_by(account_uid=uid).count() == 0

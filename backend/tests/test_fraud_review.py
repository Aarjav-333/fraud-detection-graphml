"""Test cases 2 (fraud confirmation), 6 (no duplicates) and 8 (authorization)."""
from app.models.account import Account
from app.models.account_status_event import AccountStatusEvent
from app.models.email_delivery import EmailDelivery


def review(client, headers, uid, action, **body):
    return client.post(f"/api/accounts/{uid}/review", json={"action": action, **body}, headers=headers)


def test_analyst_confirms_fraud(client, users, db, make_account, make_txn):
    uid = make_account(fraud_score=0.93, risk_level="High")
    other = make_account()
    txn = make_txn(uid, other, amount=48000, status="suspicious")

    before = client.get(f"/api/accounts/{uid}", headers=users["analyst"]).json()
    assert before["fraud_status"] == "Suspicious"          # ML/rules flagged it; nobody confirmed it
    assert before["review_status"] is None

    res = review(client, users["analyst"], uid, "under_review", note="Looking into the fan-in")
    assert res.status_code == 200 and res.json()["account"]["fraud_status"] == "Under Review"

    res = review(client, users["analyst"], uid, "confirm_fraud", note="Mule account, confirmed", transaction_uid=txn)
    body = res.json()
    assert res.status_code == 200 and body["changed"] is True
    assert body["message"] == "Account confirmed as fraud and flagged."
    account = body["account"]
    assert account["fraud_status"] == "Confirmed Fraud" and account["review_status"] == "Confirmed Fraud"
    assert account["fraud_confirmed_by"] == "t_analyst" and account["fraud_confirmed_at"]
    assert body["email"] is not None            # the holder email is queued with the confirmation

    db.expire_all()
    stored = db.query(Account).filter_by(account_uid=uid).one()
    assert stored.review_status == "Confirmed Fraud" and stored.fraud_confirmed_by == "t_analyst"
    events = db.query(AccountStatusEvent).filter_by(account_uid=uid).order_by(AccountStatusEvent.id).all()
    assert [(e.from_status, e.to_status, e.changed_by) for e in events] == [
        (None, "Under Review", "t_analyst"), ("Under Review", "Confirmed Fraud", "t_analyst")]
    assert events[1].transaction_uid == txn and events[1].note == "Mule account, confirmed"

    detail = client.get(f"/api/accounts/{uid}/investigation", headers=users["analyst"]).json()
    assert [e["to_status"] for e in detail["status_history"]] == ["Confirmed Fraud", "Under Review"]
    assert txn in [t["txn_uid"] for t in detail["transactions"]]


def test_repeated_confirmation_changes_nothing(client, users, db, make_account):
    uid = make_account()
    first = review(client, users["analyst"], uid, "confirm_fraud").json()
    again = review(client, users["analyst2"], uid, "confirm_fraud").json()
    assert first["changed"] is True and again["changed"] is False and again["email"] is None
    assert again["account"]["fraud_confirmed_by"] == "t_analyst"   # the first confirmation stands
    assert db.query(AccountStatusEvent).filter_by(account_uid=uid).count() == 1
    assert db.query(EmailDelivery).filter_by(account_uid=uid).count() == 1


def test_status_rules(client, users, make_account, make_txn):
    uid, stranger = make_account(), make_account()
    unrelated = make_txn(stranger, make_account())
    assert review(client, users["analyst"], uid, "confirm_fraud", transaction_uid=unrelated).status_code == 409
    assert review(client, users["analyst"], uid, "clear", note="x").json()["changed"] is False
    review(client, users["analyst"], uid, "confirm_fraud")
    assert review(client, users["analyst"], uid, "under_review").status_code == 409   # clear it first
    assert review(client, users["analyst"], uid, "clear").status_code == 409          # needs a reason
    cleared = review(client, users["analyst"], uid, "clear", note="Customer verified the payments").json()
    assert cleared["changed"] and cleared["account"]["fraud_status"] == "Normal"
    assert cleared["account"]["fraud_confirmed_by"] is None
    assert review(client, users["analyst"], "NOPE0000", "confirm_fraud").status_code == 404
    assert client.post(f"/api/accounts/{uid}/review", json={"action": "delete"},
                       headers=users["analyst"]).status_code == 422


def test_ml_score_is_not_a_confirmation(client, users, make_account):
    uid = make_account(fraud_score=0.99, risk_level="High")
    account = client.get(f"/api/accounts/{uid}", headers=users["analyst"]).json()
    assert account["fraud_status"] == "Suspicious" and account["fraud_confirmed_at"] is None
    found = client.get("/api/accounts", params={"q": uid, "fraud_status": "Suspicious"},
                       headers=users["analyst"]).json()
    assert [a["account_uid"] for a in found["items"]] == [uid]
    assert client.get("/api/accounts", params={"q": uid, "fraud_status": "Confirmed Fraud"},
                      headers=users["analyst"]).json()["total"] == 0


def test_only_fraud_analysts_can_review(client, users, make_account):
    uid = make_account()
    assert review(client, users["viewer"], uid, "confirm_fraud").status_code == 403
    assert client.get(f"/api/accounts/{uid}/investigation", headers=users["viewer"]).status_code == 403
    assert client.post(f"/api/accounts/{uid}/review", json={"action": "confirm_fraud"}).status_code == 401
    assert client.get(f"/api/accounts/{uid}", headers=users["viewer"]).status_code == 200   # the rest still works
    assert review(client, users["admin"], uid, "confirm_fraud").status_code == 200

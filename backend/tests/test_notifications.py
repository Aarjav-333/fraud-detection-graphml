"""Test cases 4 (real-time alert), 5 (persistence), 6 (no duplicates), 7 (disconnects), 8 (authorization)."""
import io
import time
import uuid
from datetime import datetime, timedelta

import pytest
from jose import jwt
from starlette.websockets import WebSocketDisconnect

from conftest import receive
from app.config import settings
from app.models.alert import Alert
from app.models.notification import FraudNotification
from app.models.transaction import Transaction
from app.services.notifications import notify_confirmed_fraud_activity


@pytest.fixture
def flagged(client, users, make_account):
    """An account an analyst has confirmed as fraud, and a counterparty."""
    uid = make_account(fraud_score=0.91, risk_level="High")
    res = client.post(f"/api/accounts/{uid}/review", json={"action": "confirm_fraud"}, headers=users["analyst"])
    assert res.json()["account"]["fraud_status"] == "Confirmed Fraud"
    return uid, make_account()


def pay(client, headers, sender, receiver, amount=25000, key=None):
    extra = {"Idempotency-Key": key} if key else {}
    return client.post("/api/transactions", json={"sender_uid": sender, "receiver_uid": receiver, "amount": amount},
                       headers={**headers, **extra})


def notifications_for(db, txn_uid):
    db.expire_all()
    return db.query(FraudNotification).filter_by(transaction_uid=txn_uid).all()


def connect(client, headers, after_id=None):
    ws = client.websocket_connect("/api/notifications/ws").__enter__()
    ws.send_json({"type": "auth", "token": headers["Authorization"].split()[1], "after_id": after_id})
    return ws


def disconnect(ws):
    try:
        ws.__exit__(None, None, None)
    except WebSocketDisconnect:   # the server had already closed it
        pass


def test_flagged_account_transaction_notifies_in_real_time(client, users, db, flagged):
    sender, receiver = flagged
    ws = connect(client, users["analyst"])
    try:
        ready = receive(ws)
        assert ready["type"] == "ready"
        started = time.monotonic()
        txn = pay(client, users["analyst"], sender, receiver, amount=25000).json()
        pushed = receive(ws)
        assert time.monotonic() - started < 3      # pushed when recorded, not on a polling cycle
    finally:
        disconnect(ws)

    assert pushed["type"] == "notification" and pushed["unread"] == ready["unread"] + 1
    n = pushed["notification"]
    assert n["account_uid"] == sender and n["transaction_uid"] == txn["txn_uid"]
    assert n["amount"] == 25000 and n["transaction_time"] and n["created_at"]
    assert n["account_status"] == "Confirmed Fraud" and n["risk_score"] == 0.91
    assert n["priority"] == "High" and n["read"] is False
    assert n["message"] == (f"High Priority Fraud Alert: Account {sender}, previously confirmed as fraudulent, "
                            "has initiated a new transaction of ₹25,000. Immediate investigation is recommended.")
    alert = db.query(Alert).filter_by(alert_uid=n["alert_uid"]).one()   # also on the Fraud Alerts page
    assert alert.transaction_uid == txn["txn_uid"] and alert.risk_level == "High"


def test_only_confirmed_senders_notify(client, users, db, make_account, flagged):
    flagged_uid, other = flagged
    suspicious = make_account(fraud_score=0.99, risk_level="High")    # ML says fraud; no analyst confirmed it
    for sender, receiver in [(suspicious, other), (other, flagged_uid)]:   # nor when the flagged one only receives
        txn = pay(client, users["analyst"], sender, receiver).json()
        assert notifications_for(db, txn["txn_uid"]) == []


def test_notifications_persist_across_sessions(client, users, login, db, flagged):
    sender, receiver = flagged
    txn = pay(client, users["analyst"], sender, receiver, amount=5000).json()["txn_uid"]
    note_id = notifications_for(db, txn)[0].id

    fresh_session = login("t_analyst")            # a new token, as after logging in again
    listed = client.get("/api/notifications", headers=fresh_session).json()
    item = next(i for i in listed["items"] if i["id"] == note_id)
    assert item["read"] is False and listed["unread"] >= 1

    unread = listed["unread"]
    res = client.post(f"/api/notifications/{note_id}/read", headers=fresh_session).json()
    assert res["unread"] == unread - 1
    again = client.get("/api/notifications", headers=login("t_analyst")).json()
    assert next(i for i in again["items"] if i["id"] == note_id)["read"] is True
    # read state is per analyst: still unread for the other one
    other = client.get("/api/notifications", params={"unread_only": True}, headers=users["analyst2"]).json()
    assert note_id in [i["id"] for i in other["items"]]
    client.post(f"/api/notifications/{note_id}/unread", headers=fresh_session)
    assert client.get("/api/notifications/unread-count", headers=fresh_session).json()["unread"] == unread
    client.post("/api/notifications/read-all", headers=fresh_session)
    assert client.get("/api/notifications/unread-count", headers=fresh_session).json()["unread"] == 0


def test_retries_and_repeats_dont_duplicate(client, users, db, flagged):
    sender, receiver = flagged
    key = str(uuid.uuid4())
    first = pay(client, users["analyst"], sender, receiver, key=key)
    retry = pay(client, users["analyst"], sender, receiver, key=key)
    assert first.status_code == 201 and retry.status_code == 200
    assert retry.json()["txn_uid"] == first.json()["txn_uid"]
    assert db.query(Transaction).filter_by(idempotency_key=key).count() == 1
    assert len(notifications_for(db, first.json()["txn_uid"])) == 1

    # the same event processed again (e.g. a replayed hook)
    txn = db.query(Transaction).filter_by(txn_uid=first.json()["txn_uid"]).one()
    assert notify_confirmed_fraud_activity(db, [txn]) == []
    assert len(notifications_for(db, txn.txn_uid)) == 1

    # uploading the same CSV twice
    csv = f"sender_uid,receiver_uid,amount,idempotency_key\n{sender},{receiver},700,{key}-csv\n".encode()
    up1 = client.post("/api/transactions/upload", files={"file": ("t.csv", io.BytesIO(csv), "text/csv")},
                      headers=users["analyst"]).json()
    up2 = client.post("/api/transactions/upload", files={"file": ("t.csv", io.BytesIO(csv), "text/csv")},
                      headers=users["analyst"]).json()
    assert (up1["inserted"], up2["inserted"], up2["skipped"]) == (1, 0, 1)
    uploaded = db.query(Transaction).filter_by(idempotency_key=f"{key}-csv").one()
    assert len(notifications_for(db, uploaded.txn_uid)) == 1


def test_disconnected_client_catches_up(client, users, db, flagged):
    sender, receiver = flagged
    ws = connect(client, users["analyst"])
    receive(ws)
    disconnect(ws)                 # the analyst's browser drops off

    txn = pay(client, users["analyst"], sender, receiver, amount=900)   # still recorded, no error
    assert txn.status_code == 201
    missed = notifications_for(db, txn.json()["txn_uid"])[0]

    ws = connect(client, users["analyst"], after_id=missed.id - 1)   # reconnects with what it last had
    try:
        first = receive(ws)
        assert first["type"] == "notification" and first["notification"]["id"] == missed.id
        assert receive(ws)["type"] == "ready"
    finally:
        disconnect(ws)


def test_stream_authorization(client, users):
    def closed_with(token):
        ws = client.websocket_connect("/api/notifications/ws").__enter__()
        ws.send_json({"type": "auth", "token": token})
        with pytest.raises(WebSocketDisconnect) as exc:
            receive(ws)
        disconnect(ws)
        return exc.value.code

    assert closed_with("not-a-token") == 4401
    assert closed_with(users["viewer"]["Authorization"].split()[1]) == 4403
    for path in ("/api/notifications", "/api/notifications/unread-count"):
        assert client.get(path, headers=users["viewer"]).status_code == 403
        assert client.get(path).status_code == 401


def test_stream_closes_when_the_token_expires(client):
    token = jwt.encode({"sub": "t_analyst", "exp": datetime.utcnow() + timedelta(seconds=2)},
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    ws = client.websocket_connect("/api/notifications/ws").__enter__()
    ws.send_json({"type": "auth", "token": token})
    assert receive(ws)["type"] == "ready"
    with pytest.raises(WebSocketDisconnect) as exc:
        receive(ws, timeout=6)
    disconnect(ws)
    assert exc.value.code == 4401

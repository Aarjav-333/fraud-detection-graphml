"""The risk level is computed by the rule engine only; the onboarding (KYC) risk
category is a separate, manual field that changes nothing else."""
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.migrations import run_migrations
from app.ml import rules
from app.models.account import Account
from app.models.transaction import Transaction


def create(client, headers, **fields):
    return client.post("/api/accounts", json={"customer_name": "Neha Iyer", **fields}, headers=headers)


def test_new_accounts_start_low(client, users):
    res = create(client, users["analyst"], onboarding_risk_category="High")
    body = res.json()
    assert res.status_code == 201
    assert body["risk_level"] == "Low" and body["onboarding_risk_category"] == "High"
    assert body["fraud_status"] == "Normal"     # a KYC category isn't a fraud signal


def test_risk_level_cant_be_changed_by_hand(client, users):
    res = create(client, users["analyst"], risk_level="High")
    assert res.status_code == 422 and "computed by the rule engine" in res.text
    uid = create(client, users["analyst"]).json()["account_uid"]
    res = client.put(f"/api/accounts/{uid}", json={"risk_level": "High"}, headers=users["analyst"])
    assert res.status_code == 422 and "computed by the rule engine" in res.text
    assert client.get(f"/api/accounts/{uid}", headers=users["analyst"]).json()["risk_level"] == "Low"


def test_clients_echoing_the_current_risk_level_still_work(client, users, db):
    """The previous frontend sends risk_level on every save: its current value must be accepted."""
    created = create(client, users["analyst"], email="old@client.test", phone="1", account_type="Savings",
                     risk_level="Low")
    assert created.status_code == 201
    uid = created.json()["account_uid"]
    db.query(Account).filter_by(account_uid=uid).update({"risk_level": "High"})   # as the rules would
    db.commit()
    edited = client.put(f"/api/accounts/{uid}", headers=users["analyst"], json={
        "customer_name": "Neha I.", "email": "old@client.test", "phone": "1", "account_type": "Savings",
        "risk_level": "High"})
    assert edited.status_code == 200 and edited.json()["customer_name"] == "Neha I."
    assert edited.json()["risk_level"] == "High"


def test_unknown_fields_are_refused(client, users):
    uid = create(client, users["analyst"]).json()["account_uid"]
    for body in ({"fraud_score": 0.1}, {"review_status": "Confirmed Fraud"}, {"onboarding_risk": "High"}):
        res = client.put(f"/api/accounts/{uid}", json=body, headers=users["analyst"])
        assert res.status_code == 422 and res.json()["detail"][0]["type"] == "extra_forbidden", body
    assert create(client, users["analyst"], is_fraud=1).status_code == 422


def test_customer_name_cant_be_emptied(client, users):
    uid = create(client, users["analyst"]).json()["account_uid"]
    for name in (None, "", "   "):
        assert client.put(f"/api/accounts/{uid}", json={"customer_name": name}, headers=users["analyst"]).status_code == 422
    assert create(client, users["analyst"], customer_name="").status_code == 422
    assert client.get(f"/api/accounts/{uid}", headers=users["analyst"]).json()["customer_name"] == "Neha Iyer"


def test_onboarding_category_can_be_changed_and_cleared(client, users):
    uid = create(client, users["analyst"]).json()["account_uid"]
    updated = client.put(f"/api/accounts/{uid}", json={"onboarding_risk_category": "Medium"}, headers=users["analyst"]).json()
    assert updated["onboarding_risk_category"] == "Medium" and updated["risk_level"] == "Low"
    cleared = client.put(f"/api/accounts/{uid}", json={"onboarding_risk_category": None}, headers=users["analyst"]).json()
    assert cleared["onboarding_risk_category"] is None
    bad = client.put(f"/api/accounts/{uid}", json={"onboarding_risk_category": "Severe"}, headers=users["analyst"])
    assert bad.status_code == 422


def test_unexpected_stored_category_doesnt_break_the_list(client, users, db):
    uid = create(client, users["analyst"]).json()["account_uid"]
    db.query(Account).filter_by(account_uid=uid).update({"onboarding_risk_category": "very high"})   # written outside the API
    db.commit()
    res = client.get("/api/accounts", params={"q": uid}, headers=users["analyst"])
    assert res.status_code == 200 and res.json()["items"][0]["onboarding_risk_category"] == "very high"


def test_rule_engine_sets_risk_and_leaves_onboarding_alone(tmp_path: Path):
    """On its own database: running the rules resets every account's risk level,
    which must not leak into the other tests."""
    engine = create_engine(f"sqlite:///{tmp_path.as_posix()}/rules.db")
    run_migrations(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add_all([
            Account(account_uid="K1", customer_name="A", risk_level="Low", onboarding_risk_category="Low"),
            Account(account_uid="K2", customer_name="B", risk_level="Low"),
            Transaction(txn_uid="T1", sender_uid="K2", receiver_uid="K1", amount=250_000,   # over Rs 1,00,000: R1
                        txn_type="transfer", timestamp=datetime(2024, 5, 1, 12, 0)),
        ])
        db.commit()
        rules.apply_rules(db)
        db.expire_all()
        account = db.query(Account).filter_by(account_uid="K1").one()
        assert account.risk_level in ("Medium", "High")          # raised by the rules
        assert account.onboarding_risk_category == "Low"          # untouched
    finally:
        db.close()
        engine.dispose()

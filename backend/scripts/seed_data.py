"""Load the synthetic CSVs into the database.

Run from the backend/ folder (after generate_synthetic):
    python -m scripts.seed_data
"""
import os
import pandas as pd

from app.database import SessionLocal, engine, Base
from app import models  # noqa: F401  (registers tables)
from app.models.account import Account
from app.models.transaction import Transaction

RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")


def seed():
    Base.metadata.create_all(bind=engine)
    acc_path = os.path.join(RAW, "accounts.csv")
    txn_path = os.path.join(RAW, "transactions.csv")
    if not (os.path.exists(acc_path) and os.path.exists(txn_path)):
        raise SystemExit("CSV files not found. Run first: python -m data.generate_synthetic")

    accounts = pd.read_csv(acc_path)
    txns = pd.read_csv(txn_path)

    # normalise types for a clean insert
    accounts["phone"] = accounts["phone"].astype(str)
    accounts["created_at"] = pd.to_datetime(accounts["created_at"])
    accounts["is_fraud"] = accounts["is_fraud"].astype(int)
    accounts["fraud_score"] = accounts["fraud_score"].astype(float)
    accounts["is_active"] = 1
    txns["timestamp"] = pd.to_datetime(txns["timestamp"])
    txns["is_fraud"] = txns["is_fraud"].astype(int)
    txns["amount"] = txns["amount"].astype(float)
    txns["fraud_score"] = txns["fraud_score"].astype(float)

    db = SessionLocal()
    try:
        # idempotent re-seed: clear existing app data first
        db.query(Transaction).delete()
        db.query(Account).delete()
        db.commit()

        db.bulk_insert_mappings(Account, accounts.to_dict("records"))
        db.bulk_insert_mappings(Transaction, txns.to_dict("records"))
        db.commit()
        print(f"Seeded {len(accounts)} accounts and {len(txns)} transactions.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

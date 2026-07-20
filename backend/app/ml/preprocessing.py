"""Data preprocessing / quality checks (workflow Step 5).

Detects and (optionally) cleans:
  - missing values (empty sender/receiver/amount/timestamp)
  - duplicate transactions (same sender, receiver, amount, timestamp)
  - invalid account references (sender/receiver not in the accounts table)
  - invalid amounts (<= 0)
  - invalid/missing dates
"""
import pandas as pd
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.account import Account

DUP_KEYS = ["sender_uid", "receiver_uid", "amount", "timestamp"]


def _load(db: Session):
    rows = db.query(
        Transaction.txn_uid, Transaction.sender_uid, Transaction.receiver_uid,
        Transaction.amount, Transaction.timestamp,
    ).all()
    df = pd.DataFrame(rows, columns=["txn_uid", "sender_uid", "receiver_uid", "amount", "timestamp"])
    accounts = {uid for (uid,) in db.query(Account.account_uid).all()}
    return df, accounts


def _issue_uids(df: pd.DataFrame, accounts: set) -> dict:
    if df.empty:
        return {k: set() for k in
                ["missing_fields", "duplicates", "invalid_accounts", "invalid_amounts", "invalid_dates"]}

    sender = df["sender_uid"].astype("string")
    receiver = df["receiver_uid"].astype("string")

    missing = df[sender.isna() | receiver.isna() | df["amount"].isna() | df["timestamp"].isna()
                 | (sender.str.strip() == "") | (receiver.str.strip() == "")]
    invalid_acc = df[~df["sender_uid"].isin(accounts) | ~df["receiver_uid"].isin(accounts)]
    invalid_amt = df[df["amount"].fillna(0) <= 0]
    invalid_date = df[df["timestamp"].isna()]
    duplicates = df[df.duplicated(subset=DUP_KEYS, keep="first")]

    return {
        "missing_fields": set(missing["txn_uid"]),
        "duplicates": set(duplicates["txn_uid"]),
        "invalid_accounts": set(invalid_acc["txn_uid"]),
        "invalid_amounts": set(invalid_amt["txn_uid"]),
        "invalid_dates": set(invalid_date["txn_uid"]),
    }


def analyze(db: Session) -> dict:
    df, accounts = _load(db)
    issues = _issue_uids(df, accounts)
    to_remove = set().union(*issues.values()) if issues else set()
    return {
        "total_transactions": int(len(df)),
        "total_flagged": len(to_remove),
        "issues": {
            key: {"count": len(uids), "sample": sorted(uids)[:8]}
            for key, uids in issues.items()
        },
    }


def clean(db: Session) -> dict:
    df, accounts = _load(db)
    issues = _issue_uids(df, accounts)
    to_remove = list(set().union(*issues.values())) if issues else []

    removed = 0
    for i in range(0, len(to_remove), 500):
        batch = to_remove[i:i + 500]
        removed += db.query(Transaction).filter(
            Transaction.txn_uid.in_(batch)
        ).delete(synchronize_session=False)
    db.commit()

    return {
        "removed": removed,
        "by_reason": {key: len(uids) for key, uids in issues.items()},
        "remaining": db.query(Transaction).count(),
    }

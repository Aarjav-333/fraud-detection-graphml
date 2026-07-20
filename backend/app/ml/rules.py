"""Rule-based fraud detection (workflow Step 6). Pure business logic - no ML.

Rules:
  R1 large_amount        : amount > Rs 1,00,000
  R2 rapid_transactions  : sender makes > 5 transactions within 10 minutes
  R3 new_account_large   : receiver account < 30 days old receives >= Rs 50,000
  R4 fan_in              : one account receives from >= 8 distinct senders within 1 hour
  R5 fan_out             : one account sends to >= 8 distinct receivers within 1 hour
  R6 circular            : money cycles A -> B -> C -> A within 48 hours

Running the engine:
  - marks matched transactions status='suspicious'
  - raises involved accounts' risk_level (Medium, High if hit by 2+ rules)
"""
from collections import defaultdict
from datetime import timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.account import Account

LARGE_AMOUNT = 100_000
RAPID_COUNT = 5
RAPID_WINDOW_MIN = 10
NEW_ACCOUNT_DAYS = 30
NEW_ACCOUNT_AMOUNT = 50_000
FAN_THRESHOLD = 8
FAN_WINDOW_H = 1
CIRCLE_WINDOW_H = 48

RULE_LABELS = {
    "large_amount": "R1 · Amount over ₹1,00,000",
    "rapid_transactions": "R2 · >5 txns within 10 minutes",
    "new_account_large": "R3 · New account receiving large money",
    "fan_in": "R4 · Many senders → one account",
    "fan_out": "R5 · One account → many receivers",
    "circular": "R6 · Circular transfers",
}


def _load(db: Session):
    txns = pd.DataFrame(
        db.query(Transaction.txn_uid, Transaction.sender_uid, Transaction.receiver_uid,
                 Transaction.amount, Transaction.timestamp).all(),
        columns=["txn_uid", "sender_uid", "receiver_uid", "amount", "timestamp"],
    )
    accounts = pd.DataFrame(
        db.query(Account.account_uid, Account.created_at).all(),
        columns=["account_uid", "created_at"],
    )
    return txns, accounts


def run_rules(txns: pd.DataFrame, accounts: pd.DataFrame) -> dict:
    """Return {rule_name: set(txn_uid)} for each rule."""
    hits = {name: set() for name in RULE_LABELS}
    if txns.empty:
        return hits
    txns = txns.sort_values("timestamp").reset_index(drop=True)

    # R1 large amount
    hits["large_amount"] = set(txns.loc[txns["amount"] > LARGE_AMOUNT, "txn_uid"])

    # R2 rapid transactions per sender (sliding window)
    win = timedelta(minutes=RAPID_WINDOW_MIN)
    for _, g in txns.groupby("sender_uid"):
        ts = g["timestamp"].tolist()
        uids = g["txn_uid"].tolist()
        left = 0
        for right in range(len(ts)):
            while ts[right] - ts[left] > win:
                left += 1
            if right - left + 1 > RAPID_COUNT:
                hits["rapid_transactions"].update(uids[left:right + 1])

    # R3 new account receiving large money
    acc_created = dict(zip(accounts["account_uid"], accounts["created_at"]))
    for _, row in txns[txns["amount"] >= NEW_ACCOUNT_AMOUNT].iterrows():
        created = acc_created.get(row["receiver_uid"])
        if created is not None and (row["timestamp"] - created).days < NEW_ACCOUNT_DAYS:
            hits["new_account_large"].add(row["txn_uid"])

    # R4 fan-in / R5 fan-out (distinct counterparties within a window)
    fwin = timedelta(hours=FAN_WINDOW_H)

    def fan(group_col, counter_col, out_key):
        for _, g in txns.groupby(group_col):
            g = g.reset_index(drop=True)
            ts = g["timestamp"]
            left = 0
            for right in range(len(g)):
                while ts[right] - ts[left] > fwin:
                    left += 1
                window = g.iloc[left:right + 1]
                if window[counter_col].nunique() >= FAN_THRESHOLD:
                    hits[out_key].update(window["txn_uid"])

    fan("receiver_uid", "sender_uid", "fan_in")
    fan("sender_uid", "receiver_uid", "fan_out")

    # R6 circular transfers A -> B -> C -> A (3-hop cycles within window)
    cwin = timedelta(hours=CIRCLE_WINDOW_H)
    by_sender = defaultdict(list)
    for row in txns.itertuples():
        by_sender[row.sender_uid].append(row)
    for t1 in txns.itertuples():
        a, b = t1.sender_uid, t1.receiver_uid
        if a == b:
            continue
        for t2 in by_sender.get(b, ()):
            if t2.receiver_uid in (a, b):
                continue
            if not (timedelta(0) <= t2.timestamp - t1.timestamp <= cwin):
                continue
            c = t2.receiver_uid
            for t3 in by_sender.get(c, ()):
                if t3.receiver_uid == a and timedelta(0) <= t3.timestamp - t2.timestamp <= cwin:
                    hits["circular"].update([t1.txn_uid, t2.txn_uid, t3.txn_uid])
    return hits


def apply_rules(db: Session) -> dict:
    """Run all rules, persist flags, return a summary."""
    txns, accounts = _load(db)
    hits = run_rules(txns, accounts)

    all_flagged = set().union(*hits.values()) if hits else set()

    # reset previous run, then mark suspicious
    db.query(Transaction).filter(Transaction.status == "suspicious").update(
        {"status": "normal"}, synchronize_session=False)
    flagged_list = list(all_flagged)
    for i in range(0, len(flagged_list), 500):
        db.query(Transaction).filter(Transaction.txn_uid.in_(flagged_list[i:i + 500])).update(
            {"status": "suspicious"}, synchronize_session=False)

    # account involvement: count how many rules touched each account
    uid_to_row = txns.set_index("txn_uid")[["sender_uid", "receiver_uid"]]
    acc_rule_count = defaultdict(set)
    for rule, uids in hits.items():
        for uid in uids:
            row = uid_to_row.loc[uid]
            acc_rule_count[row["sender_uid"]].add(rule)
            acc_rule_count[row["receiver_uid"]].add(rule)

    db.query(Account).update({"risk_level": "Low"}, synchronize_session=False)
    medium = [a for a, r in acc_rule_count.items() if len(r) == 1]
    high = [a for a, r in acc_rule_count.items() if len(r) >= 2]
    for chunk_vals, level in ((medium, "Medium"), (high, "High")):
        for i in range(0, len(chunk_vals), 500):
            db.query(Account).filter(Account.account_uid.in_(chunk_vals[i:i + 500])).update(
                {"risk_level": level}, synchronize_session=False)
    db.commit()

    # measure against ground truth (possible thanks to planted labels)
    truth = pd.DataFrame(
        db.query(Transaction.txn_uid, Transaction.is_fraud).all(),
        columns=["txn_uid", "is_fraud"],
    )
    truth["flagged"] = truth["txn_uid"].isin(all_flagged)
    tp = int(((truth["is_fraud"] == 1) & truth["flagged"]).sum())
    fp = int(((truth["is_fraud"] == 0) & truth["flagged"]).sum())
    fn = int(((truth["is_fraud"] == 1) & ~truth["flagged"]).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0

    return {
        "total_transactions": int(len(txns)),
        "total_suspicious": len(all_flagged),
        "rules": [
            {"rule": name, "label": RULE_LABELS[name], "count": len(uids)}
            for name, uids in hits.items()
        ],
        "accounts_risk": {"medium": len(medium), "high": len(high)},
        "evaluation": {
            "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
        },
    }

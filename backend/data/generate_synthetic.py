"""Generate a synthetic banking dataset with planted fraud patterns.

Writes:
  data/raw/accounts.csv
  data/raw/transactions.csv

Fraud patterns planted (mirroring the project's rule-based checks):
  - Fraud rings: many source accounts -> one mule -> a withdrawal account (fan-in)
  - Structuring / smurfing: many transactions just under Rs 1,00,000 within minutes
  - Circular transfers: A -> B -> C -> A
  - Fan-out: one account paying many accounts rapidly

Run from the backend/ folder:
    python -m data.generate_synthetic
"""
import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# ----------------------------- config -----------------------------
SEED = 42
N_ACCOUNTS = 5000
TARGET_TXNS = 80000
LARGE_AMOUNT = 100000            # Rs 1,00,000 threshold from the rule doc
START_DATE = datetime(2024, 1, 1)
DAYS_SPAN = 365

N_RINGS = 60                     # fraud rings
N_STRUCTURING = 120              # structuring/smurfing groups
N_CIRCULAR = 90                  # circular transfer groups
N_FANOUT = 50                    # fan-out groups
N_NEW_ACCOUNT = 40               # new-account large-deposit patterns

OUT_DIR = os.path.join(os.path.dirname(__file__), "raw")

ACCOUNT_TYPES = ["Savings", "Current", "Wallet", "Business"]
TXN_TYPES = ["transfer", "payment", "withdrawal"]

fake = Faker("en_IN")
Faker.seed(SEED)
random.seed(SEED)
np.random.seed(SEED)

txns = []
fraud_accounts = set()
_counter = {"n": 0}


def rand_time():
    return START_DATE + timedelta(
        days=random.randint(0, DAYS_SPAN),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )


def add_txn(sender, receiver, amount, ts, ttype, is_fraud):
    _counter["n"] += 1
    txns.append({
        "txn_uid": f"TXN{_counter['n']:07d}",
        "sender_uid": sender,
        "receiver_uid": receiver,
        "amount": round(float(amount), 2),
        "timestamp": ts,
        "txn_type": ttype,
        "status": "normal",     # system fills this later
        "is_fraud": int(is_fraud),
        "fraud_score": 0.0,     # system fills this later
    })


def build_accounts(n):
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "account_uid": f"ACC{i:05d}",
            "customer_name": fake.name(),
            "email": fake.email(),
            "phone": fake.msisdn(),
            "account_type": random.choice(ACCOUNT_TYPES),
            "created_at": START_DATE - timedelta(days=random.randint(1, 900)),
            "risk_level": "Low",
            "fraud_score": 0.0,
            "is_fraud": 0,
        })
    return rows


def plant_normal(count, uids):
    for _ in range(count):
        s, r = random.sample(uids, 2)
        amt = min(round(np.random.lognormal(mean=8.0, sigma=1.0), 2), 95000)
        add_txn(s, r, amt, rand_time(), random.choice(TXN_TYPES), 0)


def plant_rings(n, uids):
    for _ in range(n):
        members = random.sample(uids, random.randint(10, 16))
        mule, withdrawal, sources = members[0], members[1], members[2:]
        fraud_accounts.update(members)
        base = rand_time()
        total = 0
        for s in sources:                       # fan-in: many -> mule
            amt = random.randint(20000, 90000)
            total += amt
            add_txn(s, mule, amt, base + timedelta(minutes=random.randint(0, 30)), "transfer", 1)
        add_txn(mule, withdrawal, total * 0.95,  # mule -> withdrawal
                base + timedelta(hours=1), "withdrawal", 1)


def plant_structuring(n, uids):
    for _ in range(n):
        s, r = random.sample(uids, 2)
        fraud_accounts.update([s, r])
        base = rand_time()
        for _ in range(random.randint(6, 12)):  # many small txns within 10 min
            amt = random.randint(90000, 99000)   # just under the threshold
            add_txn(s, r, amt, base + timedelta(minutes=random.randint(0, 9)), "transfer", 1)


def plant_circular(n, uids):
    for _ in range(n):
        a, b, c = random.sample(uids, 3)
        fraud_accounts.update([a, b, c])
        base = rand_time()
        amt = random.randint(30000, 90000)
        add_txn(a, b, amt, base, "transfer", 1)
        add_txn(b, c, amt * 0.98, base + timedelta(minutes=random.randint(1, 20)), "transfer", 1)
        add_txn(c, a, amt * 0.96, base + timedelta(minutes=random.randint(1, 20)), "transfer", 1)


def plant_fanout(n, uids):
    for _ in range(n):
        members = random.sample(uids, random.randint(8, 15))
        src, targets = members[0], members[1:]
        fraud_accounts.update(members)
        base = rand_time()
        for t in targets:                        # one -> many, rapidly
            add_txn(src, t, random.randint(15000, 80000),
                    base + timedelta(minutes=random.randint(0, 9)), "transfer", 1)


def plant_new_account_deposits(n, accounts):
    """Fraud pattern: a freshly created account immediately receives large sums."""
    others = [a["account_uid"] for a in accounts]
    chosen = random.sample(accounts, n)
    for acc in chosen:
        # make the account recently created within the transaction year
        created = START_DATE + timedelta(days=random.randint(0, DAYS_SPAN - 40))
        acc["created_at"] = created
        fraud_accounts.add(acc["account_uid"])
        base = created + timedelta(days=random.randint(1, 20))
        for _ in range(random.randint(2, 4)):
            sender = random.choice(others)
            while sender == acc["account_uid"]:
                sender = random.choice(others)
            fraud_accounts.add(sender)
            add_txn(sender, acc["account_uid"], random.randint(60000, 95000),
                    base + timedelta(hours=random.randint(0, 72)), "transfer", 1)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    accounts = build_accounts(N_ACCOUNTS)
    uids = [a["account_uid"] for a in accounts]

    plant_rings(N_RINGS, uids)
    plant_structuring(N_STRUCTURING, uids)
    plant_circular(N_CIRCULAR, uids)
    plant_fanout(N_FANOUT, uids)
    plant_new_account_deposits(N_NEW_ACCOUNT, accounts)
    fraud_count = len(txns)

    plant_normal(max(0, TARGET_TXNS - fraud_count), uids)

    # shuffle, order by time, then assign clean sequential ids
    random.shuffle(txns)
    txn_df = pd.DataFrame(txns).sort_values("timestamp").reset_index(drop=True)
    txn_df["txn_uid"] = [f"TXN{i:07d}" for i in range(1, len(txn_df) + 1)]

    acc_df = pd.DataFrame(accounts)
    acc_df["is_fraud"] = acc_df["account_uid"].isin(fraud_accounts).astype(int)

    acc_df.to_csv(os.path.join(OUT_DIR, "accounts.csv"), index=False)
    txn_df.to_csv(os.path.join(OUT_DIR, "transactions.csv"), index=False)

    print(f"Accounts     : {len(acc_df):>6}  (fraud accounts: {int(acc_df['is_fraud'].sum())})")
    print(f"Transactions : {len(txn_df):>6}  (fraud txns: {int(txn_df['is_fraud'].sum())}, "
          f"{100 * txn_df['is_fraud'].mean():.2f}%)")
    print(f"Saved to {OUT_DIR}/accounts.csv and transactions.csv")


if __name__ == "__main__":
    main()

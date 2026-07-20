"""Feature engineering (workflow Step 9).

Builds one feature row per account by combining:
  Transaction features : totals, counts, unique counterparties, averages, frequency
  Graph features       : degree, centrality, PageRank, cycle membership, community size
Label                  : is_fraud (ground truth from the synthetic data)

The matrix is saved to data/processed/features.csv and reused by the ML models (Phase 9).
"""
import os
from collections import defaultdict

import pandas as pd
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.graph_metric import GraphMetric

PROCESSED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "processed",
)
FEATURES_CSV = os.path.join(PROCESSED_DIR, "features.csv")

FEATURE_DESCRIPTIONS = {
    "total_sent": "Total amount the account sent",
    "total_received": "Total amount the account received",
    "txn_count_sent": "Number of transactions sent",
    "txn_count_received": "Number of transactions received",
    "unique_receivers": "Distinct accounts it sent money to",
    "unique_senders": "Distinct accounts it received money from",
    "avg_sent_amount": "Average amount per sent transaction",
    "avg_received_amount": "Average amount per received transaction",
    "max_sent_amount": "Largest single sent transaction",
    "max_received_amount": "Largest single received transaction",
    "txn_per_active_day": "Transaction frequency (txns per active day)",
    "in_degree": "Graph: distinct senders paying this account",
    "out_degree": "Graph: distinct receivers this account pays",
    "degree_centrality": "Graph: normalized connectedness",
    "pagerank": "Graph: importance in the money network",
    "in_cycle": "Graph: participates in a short money loop (0/1)",
    "community_size": "Graph: size of the account's community",
}


def build_features(db: Session) -> pd.DataFrame:
    # --- transaction-level aggregates ---
    agg = defaultdict(lambda: {
        "total_sent": 0.0, "total_received": 0.0,
        "txn_count_sent": 0, "txn_count_received": 0,
        "receivers": set(), "senders": set(),
        "max_sent": 0.0, "max_received": 0.0,
        "days": set(),
    })
    rows = db.query(
        Transaction.sender_uid, Transaction.receiver_uid,
        Transaction.amount, Transaction.timestamp,
    ).all()
    for sender, receiver, amount, ts in rows:
        s, r = agg[sender], agg[receiver]
        s["total_sent"] += amount
        s["txn_count_sent"] += 1
        s["receivers"].add(receiver)
        s["max_sent"] = max(s["max_sent"], amount)
        s["days"].add(ts.date())
        r["total_received"] += amount
        r["txn_count_received"] += 1
        r["senders"].add(sender)
        r["max_received"] = max(r["max_received"], amount)
        r["days"].add(ts.date())

    # --- graph metrics ---
    gm = {
        m.account_uid: m
        for m in db.query(GraphMetric).all()
    }

    # --- labels + assembly ---
    records = []
    for uid, label in db.query(Account.account_uid, Account.is_fraud).all():
        a = agg[uid]
        g = gm.get(uid)
        n_days = max(len(a["days"]), 1)
        n_txn = a["txn_count_sent"] + a["txn_count_received"]
        records.append({
            "account_uid": uid,
            "total_sent": round(a["total_sent"], 2),
            "total_received": round(a["total_received"], 2),
            "txn_count_sent": a["txn_count_sent"],
            "txn_count_received": a["txn_count_received"],
            "unique_receivers": len(a["receivers"]),
            "unique_senders": len(a["senders"]),
            "avg_sent_amount": round(a["total_sent"] / a["txn_count_sent"], 2) if a["txn_count_sent"] else 0.0,
            "avg_received_amount": round(a["total_received"] / a["txn_count_received"], 2) if a["txn_count_received"] else 0.0,
            "max_sent_amount": round(a["max_sent"], 2),
            "max_received_amount": round(a["max_received"], 2),
            "txn_per_active_day": round(n_txn / n_days, 4),
            "in_degree": g.in_degree if g else 0,
            "out_degree": g.out_degree if g else 0,
            "degree_centrality": g.degree_centrality if g else 0.0,
            "pagerank": g.pagerank if g else 0.0,
            "in_cycle": g.in_cycle if g else 0,
            "community_size": g.community_size if g else 0,
            "is_fraud": int(label or 0),
        })
    return pd.DataFrame(records)


def build_and_save(db: Session) -> dict:
    df = build_features(db)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    df.to_csv(FEATURES_CSV, index=False)
    n_fraud = int(df["is_fraud"].sum())
    return {
        "accounts": int(len(df)),
        "features": len(FEATURE_DESCRIPTIONS),
        "fraud_accounts": n_fraud,
        "fraud_ratio": round(n_fraud / len(df), 4) if len(df) else 0.0,
        "graph_metrics_joined": bool(db.query(GraphMetric).count()),
        "saved_to": "data/processed/features.csv",
        "feature_list": [
            {"name": k, "description": v} for k, v in FEATURE_DESCRIPTIONS.items()
        ],
    }


def load_features() -> pd.DataFrame | None:
    if os.path.exists(FEATURES_CSV):
        return pd.read_csv(FEATURES_CSV)
    return None

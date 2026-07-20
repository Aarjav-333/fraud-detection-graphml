"""Fraud ring detection (workflow Step 12).

A fraud ring = a connected group of suspicious accounts moving money together
(e.g. many source accounts -> a main/mule account -> a withdrawal account).

Method:
  1. Take the subgraph of "suspicious activity": edges from transactions marked
     suspicious by the rule engine, plus accounts with high ML fraud scores.
  2. Find weakly connected components with >= MIN_RING_SIZE members.
  3. For each ring, assign roles from money flow:
        main       - highest total received inside the ring
        withdrawal - receives from the main account and sends little onwards
        source     - everyone else (feeding money in)
  4. Score each ring by average member fraud score and total money moved.

Results are cached to saved_models/rings.json for the UI.
"""
import os
import json
from collections import defaultdict

import networkx as nx
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.account import Account

SAVED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_models")
RINGS_JSON = os.path.join(SAVED_DIR, "rings.json")

MIN_RING_SIZE = 4
ML_SCORE_FLOOR = 0.7      # accounts above this join the suspicious subgraph
MAX_RING_MEMBERS_SHOWN = 40


def detect(db: Session) -> dict:
    scores = dict(db.query(Account.account_uid, Account.fraud_score).all())
    names = dict(db.query(Account.account_uid, Account.customer_name).all())
    truth = dict(db.query(Account.account_uid, Account.is_fraud).all())

    # 1) suspicious-activity subgraph
    G = nx.DiGraph()
    sus_txns = db.query(
        Transaction.sender_uid, Transaction.receiver_uid, Transaction.amount,
    ).filter(Transaction.status == "suspicious").all()
    for s, r, amt in sus_txns:
        if G.has_edge(s, r):
            G[s][r]["amount"] += amt
            G[s][r]["count"] += 1
        else:
            G.add_edge(s, r, amount=float(amt), count=1)

    # connect high-ML-score accounts through their transactions with each other
    hot = {uid for uid, sc in scores.items() if (sc or 0) >= ML_SCORE_FLOOR}
    if hot:
        hot_txns = db.query(
            Transaction.sender_uid, Transaction.receiver_uid, Transaction.amount,
        ).filter(Transaction.sender_uid.in_(hot),
                 Transaction.receiver_uid.in_(hot)).all()
        for s, r, amt in hot_txns:
            if G.has_edge(s, r):
                G[s][r]["amount"] += amt
                G[s][r]["count"] += 1
            else:
                G.add_edge(s, r, amount=float(amt), count=1)

    # 2) connected groups; split oversized components into communities so
    #    distinct rings inside one big suspicious blob separate out
    MAX_COMPONENT = 60
    groups = []
    for comp in nx.weakly_connected_components(G):
        if len(comp) < MIN_RING_SIZE:
            continue
        if len(comp) <= MAX_COMPONENT:
            groups.append(comp)
            continue
        sub_u = G.subgraph(comp).to_undirected()
        for com in nx.community.louvain_communities(sub_u, seed=42, resolution=2.0):
            if len(com) >= MIN_RING_SIZE:
                groups.append(set(com))

    rings = []
    for comp in groups:
        sub = G.subgraph(comp)
        received = {u: 0.0 for u in comp}
        sent = {u: 0.0 for u in comp}
        for u, v, d in sub.edges(data=True):
            sent[u] += d["amount"]
            received[v] += d["amount"]

        # 3) roles
        main = max(comp, key=lambda u: received[u])
        withdrawal = None
        outs = sorted(G.successors(main), key=lambda v: G[main][v]["amount"], reverse=True)
        for v in outs:
            if v in comp and sent.get(v, 0) <= received.get(v, 0):
                withdrawal = v
                break
        roles = {}
        for u in comp:
            if u == main:
                roles[u] = "main"
            elif u == withdrawal:
                roles[u] = "withdrawal"
            else:
                roles[u] = "source"

        member_scores = [scores.get(u, 0.0) or 0.0 for u in comp]
        avg_score = sum(member_scores) / len(member_scores)
        total_flow = sum(d["amount"] for _, _, d in sub.edges(data=True))
        risk = "High" if avg_score >= 0.8 else ("Medium" if avg_score >= 0.5 else "Low")
        fraud_members = sum(1 for u in comp if truth.get(u))

        members = sorted(comp, key=lambda u: received[u], reverse=True)[:MAX_RING_MEMBERS_SHOWN]
        rings.append({
            "ring_id": f"RING{len(rings) + 1:03d}",
            "size": len(comp),
            "main_account": main,
            "main_name": names.get(main, main),
            "withdrawal_account": withdrawal,
            "total_flow": round(total_flow, 2),
            "avg_fraud_score": round(avg_score, 4),
            "risk": risk,
            "ground_truth_fraud_members": fraud_members,
            "nodes": [
                {"id": u, "name": names.get(u, u), "role": roles[u],
                 "fraud_score": round(scores.get(u, 0.0) or 0.0, 3),
                 "received": round(received[u], 2), "sent": round(sent[u], 2)}
                for u in members
            ],
            "links": [
                {"source": u, "target": v,
                 "amount": round(d["amount"], 2), "count": d["count"]}
                for u, v, d in sub.edges(data=True)
                if u in set(members) and v in set(members)
            ],
        })

    rings.sort(key=lambda r: (r["avg_fraud_score"], r["total_flow"]), reverse=True)
    summary = {
        "rings_found": len(rings),
        "accounts_involved": sum(r["size"] for r in rings),
        "total_flow": round(sum(r["total_flow"] for r in rings), 2),
        "high_risk_rings": sum(1 for r in rings if r["risk"] == "High"),
        "rings": rings,
    }
    os.makedirs(SAVED_DIR, exist_ok=True)
    with open(RINGS_JSON, "w") as fh:
        json.dump(summary, fh)
    return summary


def load_rings() -> dict | None:
    if os.path.exists(RINGS_JSON):
        with open(RINGS_JSON) as fh:
            return json.load(fh)
    return None

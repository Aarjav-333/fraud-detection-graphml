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
  4. Score each ring on two signals: the members' average ML fraud score, and a
     rule score - how many different rules (R1-R6) fired on the ring's own
     transactions (1 rule = 0.33, 2 = 0.67, 3+ = 1.0). Risk uses the stronger
     of the two, so a ring the rules caught several ways is not rated Low just
     because the ML model has not seen the pattern, while one rule alone is not
     enough to lift a ring to Medium.

Results are cached to saved_models/rings.json for the UI.
"""
import os
import json
from collections import defaultdict

import networkx as nx
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.alerts import score_to_risk
from app.ml.rules import RULE_CODES
from app.models.transaction import Transaction
from app.models.account import Account
from app.models.rule_hit import RuleHit

MIN_RING_SIZE = 4
ML_SCORE_FLOOR = 0.7      # accounts above this join the suspicious subgraph
MAX_RING_MEMBERS_SHOWN = 40
RULES_FOR_FULL_SCORE = 3  # distinct rules on a ring's own transactions for rule score 1.0
DETAIL_KEYS = ("nodes", "links", "member_ids")


def _add_edge(G: nx.DiGraph, sender: str, receiver: str, amount: float) -> None:
    if G.has_edge(sender, receiver):
        G[sender][receiver]["amount"] += amount
        G[sender][receiver]["count"] += 1
    else:
        G.add_edge(sender, receiver, amount=float(amount), count=1, rules=set())


def detect(db: Session) -> dict:
    scores, names, truth = {}, {}, {}
    for uid, score, name, is_fraud in db.query(
            Account.account_uid, Account.fraud_score, Account.customer_name, Account.is_fraud):
        scores[uid], names[uid], truth[uid] = score, name, is_fraud
    rules_by_txn = defaultdict(set)
    for txn_uid, rule in db.query(RuleHit.txn_uid, RuleHit.rule):
        rules_by_txn[txn_uid].add(rule)

    # 1) suspicious-activity subgraph; each edge remembers which rules fired on it
    G = nx.DiGraph()
    sus_txns = db.query(
        Transaction.txn_uid, Transaction.sender_uid, Transaction.receiver_uid, Transaction.amount,
    ).filter(Transaction.status == "suspicious").all()
    for txn_uid, s, r, amt in sus_txns:
        _add_edge(G, s, r, amt)
        G[s][r]["rules"] |= rules_by_txn.get(txn_uid, set())

    # connect high-ML-score accounts through their transactions with each other
    hot = {uid for uid, sc in scores.items() if (sc or 0) >= ML_SCORE_FLOOR}
    if hot:
        hot_txns = db.query(
            Transaction.sender_uid, Transaction.receiver_uid, Transaction.amount,
        ).filter(Transaction.sender_uid.in_(hot),
                 Transaction.receiver_uid.in_(hot)).all()
        for s, r, amt in hot_txns:
            _add_edge(G, s, r, amt)

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
        ring_rules = set().union(*(d["rules"] for _, _, d in sub.edges(data=True)))
        rule_score = min(len(ring_rules), RULES_FOR_FULL_SCORE) / RULES_FOR_FULL_SCORE
        risk_score = max(avg_score, rule_score)
        total_flow = sum(d["amount"] for _, _, d in sub.edges(data=True))
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
            "rules": sorted(RULE_CODES[r] for r in ring_rules),
            "rule_score": round(rule_score, 4),
            "risk_score": round(risk_score, 4),
            "risk": score_to_risk(risk_score),
            "ground_truth_fraud_members": fraud_members,
            "member_ids": sorted(comp),     # full membership; "nodes" is capped for display
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

    rings.sort(key=lambda r: (r["risk_score"], r["total_flow"]), reverse=True)
    summary = {
        "rings_found": len(rings),
        "accounts_involved": sum(r["size"] for r in rings),
        "total_flow": round(sum(r["total_flow"] for r in rings), 2),
        "high_risk_rings": sum(1 for r in rings if r["risk"] == "High"),
        "rings": rings,
    }
    os.makedirs(settings.saved_models_dir, exist_ok=True)
    with open(_rings_json(), "w") as fh:
        json.dump(summary, fh)
    return summary


def ring_summary(ring: dict) -> dict:
    """A ring without its per-member detail, for list views."""
    return {k: v for k, v in ring.items() if k not in DETAIL_KEYS}


def _rings_json() -> str:
    return os.path.join(settings.saved_models_dir, "rings.json")


def load_rings() -> dict | None:
    if os.path.exists(_rings_json()):
        with open(_rings_json()) as fh:
            return json.load(fh)
    return None

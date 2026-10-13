"""How detection did on the demo scenario, read from what the pipeline recorded.

Per stage: which scripted transactions were flagged, by which rules, and
whether the rules the stage is designed to trigger fired. Plus each account's
role, risk level and review status, the fraud rings holding the scenario, and
the money-flow network. Everything comes from the rule hits, alerts and rings
the real rule engine and ring detection stored - nothing is assumed here.
"""
from collections import Counter, defaultdict

from sqlalchemy import and_, not_, or_
from sqlalchemy.orm import Session

from app.demo.scenario import (BACKGROUND_END, BACKGROUND_PREFIX, NAMES, ROLES, STAGE_INFO, STAGES,
                               scenario_transactions)
from app.ml.fraud_ring import load_rings
from app.ml.rules import RULE_CODES, RULE_LABELS
from app.models.account import Account
from app.models.alert import Alert
from app.models.graph_metric import GraphMetric
from app.models.rule_hit import RuleHit
from app.models.transaction import Transaction

RULE_NAMES = {RULE_CODES[name]: label for name, label in RULE_LABELS.items()}   # "R4" -> "R4 · Many senders → one account"
ALL_RULES = sorted(RULE_NAMES)
RECENT_EXTRA = 20


def _iso(value):
    return value.isoformat() if value else None


def report(db: Session) -> dict | None:
    """The scenario's detection coverage, or None if it isn't in this database."""
    account_uids = list(ROLES)
    accounts = {a.account_uid: a for a in db.query(Account).filter(Account.account_uid.in_(account_uids))}
    if not accounts:
        return None
    scripted = scenario_transactions()
    scripted_uids = [row["txn_uid"] for _, row in scripted]
    txns = {t.txn_uid: t for t in db.query(Transaction).filter(Transaction.txn_uid.in_(scripted_uids))}
    hits = defaultdict(set)
    for txn_uid, rule in db.query(RuleHit.txn_uid, RuleHit.rule).filter(RuleHit.txn_uid.in_(scripted_uids)):
        hits[txn_uid].add(RULE_CODES.get(rule, rule))
    alerts_by_txn = Counter(uid for (uid,) in db.query(Alert.transaction_uid)
                            .filter(Alert.transaction_uid.in_(scripted_uids)))
    alerts_by_account = Counter(uid for (uid,) in db.query(Alert.account_uid)
                                .filter(Alert.account_uid.in_(account_uids)))

    stages = []
    for number, stage in enumerate(STAGES, start=1):
        info = STAGE_INFO[stage]
        items = []
        for _, row in (pair for pair in scripted if pair[0] == stage):
            t = txns.get(row["txn_uid"])
            items.append({
                "txn_uid": row["txn_uid"],
                "sender_uid": row["sender_uid"], "sender_role": ROLES[row["sender_uid"]],
                "receiver_uid": row["receiver_uid"], "receiver_role": ROLES[row["receiver_uid"]],
                "amount": t.amount if t else row["amount"],
                "timestamp": _iso(t.timestamp if t else row["timestamp"]),
                "status": t.status if t else "missing",
                "rules": sorted(hits[row["txn_uid"]]),
                "alerts": alerts_by_txn[row["txn_uid"]],
            })
        fired = Counter(code for item in items for code in item["rules"])
        expected = info["expected_rules"]
        stages.append({
            "stage": stage, "number": number, "name": info["name"], "description": info["description"],
            "expected_rules": expected,
            "rules_fired": dict(sorted(fired.items())),
            "detected": all(fired[r] for r in expected),
            "flagged": sum(item["status"] == "suspicious" for item in items),
            "total": len(items),
            "amount": round(sum(item["amount"] for item in items), 2),
            "transactions": items,
        })

    rings_data = load_rings() or {}
    rings = []
    ring_of = {}
    for ring in rings_data.get("rings", []):
        members = set(ring.get("member_ids", []))
        overlap = members & set(account_uids)
        if overlap:
            ring_of.update({uid: ring["ring_id"] for uid in overlap})
            rings.append({
                "ring_id": ring["ring_id"], "size": ring["size"],
                "scenario_members": len(overlap), "other_members": len(members - overlap),
                "main_account": ring["main_account"], "withdrawal_account": ring.get("withdrawal_account"),
                "rules": ring.get("rules", []), "risk": ring["risk"], "total_flow": ring["total_flow"],
                "avg_fraud_score": ring.get("avg_fraud_score"),   # model output: not shown in the standalone demo
            })

    # the money-flow network between the scenario's accounts, and anything recorded after it was
    # planted - not the ordinary background activity the demo copy plants around it
    flows = defaultdict(lambda: {"amount": 0.0, "count": 0})
    involved = or_(Transaction.sender_uid.in_(account_uids), Transaction.receiver_uid.in_(account_uids))
    background = and_(Transaction.txn_uid >= BACKGROUND_PREFIX, Transaction.txn_uid < BACKGROUND_END)
    extra = []
    for t in db.query(Transaction).filter(involved, not_(background)).order_by(Transaction.timestamp):
        if t.sender_uid in accounts and t.receiver_uid in accounts:
            flow = flows[(t.sender_uid, t.receiver_uid)]
            flow["amount"] += t.amount
            flow["count"] += 1
        if t.txn_uid not in txns:
            extra.append(t)

    fired_all = sorted({code for stage in stages for code in stage["rules_fired"]})
    names = dict(zip(ROLES, NAMES))
    return {
        "database": {"accounts": db.query(Account.id).count(), "transactions": db.query(Transaction.id).count()},
        "pipeline": {
            "rules_run": db.query(RuleHit.id).first() is not None,
            "graph_run": db.query(GraphMetric.id).first() is not None,
            "rings_run": bool(rings_data),
            "alerts_generated": sum(alerts_by_account.values()) > 0 or sum(alerts_by_txn.values()) > 0,
        },
        "coverage": {
            "transactions_total": len(scripted), "transactions_flagged": sum(s["flagged"] for s in stages),
            "stages_total": len(stages), "stages_detected": sum(s["detected"] for s in stages),
            "rules_expected": ALL_RULES, "rules_fired": fired_all,
            "all_rules_fired": fired_all == ALL_RULES,
            "accounts_total": len(account_uids), "accounts_in_rings": len(ring_of),
        },
        "rule_labels": RULE_NAMES,
        "stages": stages,
        "accounts": [{
            "account_uid": uid, "customer_name": accounts[uid].customer_name if uid in accounts else names[uid],
            "role": ROLES[uid], "account_type": accounts[uid].account_type if uid in accounts else None,
            "risk_level": accounts[uid].risk_level if uid in accounts else None,
            "fraud_status": accounts[uid].fraud_status if uid in accounts else None,
            "fraud_score": accounts[uid].fraud_score if uid in accounts else None,   # not shown in the standalone demo
            "alerts": alerts_by_account[uid],
            "ring_id": ring_of.get(uid),
        } for uid in account_uids],
        "rings": rings,
        "graph": {
            "nodes": [{"id": uid, "name": names[uid], "role": ROLES[uid],
                       "risk_level": accounts[uid].risk_level if uid in accounts else None,
                       "fraud_status": accounts[uid].fraud_status if uid in accounts else None}
                      for uid in account_uids],
            "links": [{"source": s, "target": r, "amount": round(f["amount"], 2), "count": f["count"]}
                      for (s, r), f in flows.items()],
        },
        "other_transactions": {
            "count": len(extra),
            "recent": [{"txn_uid": t.txn_uid, "sender_uid": t.sender_uid, "receiver_uid": t.receiver_uid,
                        "amount": t.amount, "timestamp": _iso(t.timestamp), "status": t.status}
                       for t in extra[-RECENT_EXTRA:][::-1]],
        },
    }

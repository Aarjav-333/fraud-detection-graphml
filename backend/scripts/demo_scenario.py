"""Plant a scripted fraud operation and run the full detection pipeline on it.

Made for live demos and the project report: every run plants the same accounts
and transactions, so the story is repeatable and easy to find in the UI
(search for "DEMO-").

The scenario - a mule network laundering money (all ids start with DEMO-):
  1. Collection    9 feeder accounts pay a mule account opened 6 days earlier,
                   all within 25 minutes                  -> R4 fan-in, R3 new account
  2. Consolidation the mule forwards everything to a collector -> R1 large amount
  3. Layering      collector -> shell 1 -> shell 2 -> collector, each hop kept
                   under Rs 1,00,000 so R1 misses it           -> R6 circular
  4. Cash-out      the collector splits money into 9 transfers just under
                   Rs 1,00,000 to 9 cash-out accounts in 8 minutes -> R2 rapid, R5 fan-out

Like every account in the synthetic dataset, each demo account also gets ~30
ordinary transactions with real customers over 2024, so it looks like a normal
customer to the graph and ML steps instead of an isolated island.

Demo accounts are inserted with is_fraud=0 (an operation nobody has confirmed
yet), so the supervised model is never told they are fraud: a high ML score is
the model generalizing, not memorizing. Side effect: the rule engine's precision
figure counts the demo transactions as false positives.

Run from the backend/ folder, after init_db + seed_data:
    python -m scripts.demo_scenario               # plant + run pipeline + report
    python -m scripts.demo_scenario --plant-only  # plant, then click through the UI
    python -m scripts.demo_scenario --cleanup     # remove the demo again

The pipeline steps are the same ones the UI runs, in the sidebar's order, so they
refresh scores, alerts and rings for the whole dataset - and retraining with the
demo present can raise alerts on real accounts too. Re-planting and --cleanup
therefore remove, besides all demo data, every alert raised since the demo was
planted that nobody has worked on yet (still Pending, no case). --cleanup then
re-runs every step except alert generation, so scores, features and rings no
longer include the demo.
"""
import argparse
import json
import os
import random
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select

from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401  (registers tables)
from app.ml import alerts as alert_engine
from app.ml import baseline, features, fraud_ring, graph_analysis
from app.ml import rules as rules_engine
from app.models.account import Account
from app.models.alert import Alert
from app.models.case import Case
from app.models.graph_metric import GraphMetric
from app.models.rule_hit import RuleHit
from app.models.transaction import Transaction

PREFIX = "DEMO-"
BASE = datetime(2024, 11, 14, 1, 30)   # a night inside the synthetic data's 2024 range
ML_ALERT_THRESHOLD = 0.8               # same default as the Fraud Alerts page
YEAR_START, YEAR_END = datetime(2024, 1, 1), datetime(2024, 12, 31, 23, 59)
QUIET_BEFORE, QUIET_AFTER = timedelta(days=1), timedelta(days=2)  # no background txns near the scenario
STATE_JSON = os.path.join(fraud_ring.SAVED_DIR, "demo_state.json")  # gitignored, like rings.json

FEEDERS = [f"{PREFIX}FEED{i:02d}" for i in range(1, 10)]
MULE = f"{PREFIX}MULE"
COLLECTOR = f"{PREFIX}COLLECTOR"
SHELLS = [f"{PREFIX}SHELL1", f"{PREFIX}SHELL2"]
CASHOUTS = [f"{PREFIX}CASH{i:02d}" for i in range(1, 10)]

ROLES = {
    **{u: "feeder" for u in FEEDERS},
    MULE: "mule",
    COLLECTOR: "collector",
    **{u: "shell" for u in SHELLS},
    **{u: "cash-out" for u in CASHOUTS},
}
NAMES = [
    "Ritika Bansal", "Harish Kulkarni", "Meera Pillai", "Sanjay Rawat", "Ayesha Khan",
    "Gopal Iyer", "Nandini Rao", "Vikram Sethi", "Pooja Chawla",          # feeders
    "Kabir Malhotra",                                                      # mule
    "Raghav Oberoi",                                                       # collector
    "Sterling Traders", "Lotus Exim Services",                             # shells
    "Imran Shaikh", "Deepa Menon", "Tarun Gill", "Lakshmi Reddy", "Aman Bedi",
    "Sunita Joshi", "Farhan Qureshi", "Kavya Nair", "Rohit Dhawan",        # cash-outs
]
STAGES = ["1 Collection", "2 Consolidation", "3 Layering", "4 Cash-out"]

# ASCII labels so the report prints on any Windows console or pipe
RULE_SHORT = {
    "large_amount": "R1 large amount",
    "rapid_transactions": "R2 rapid",
    "new_account_large": "R3 new account",
    "fan_in": "R4 fan-in",
    "fan_out": "R5 fan-out",
    "circular": "R6 circular",
}


def _is_demo(column):
    # A case-sensitive prefix match. Not LIKE 'DEMO-%': SQLite's LIKE ignores
    # case, so it would also match (and delete) a real account named "demo-...".
    return func.substr(column, 1, len(PREFIX)) == PREFIX


def _accounts() -> list[dict]:
    created = {u: BASE - timedelta(days=300 + 37 * i) for i, u in enumerate(FEEDERS)}
    created[MULE] = BASE - timedelta(days=6)            # brand-new account -> R3
    created[COLLECTOR] = BASE - timedelta(days=500)
    created.update({SHELLS[0]: BASE - timedelta(days=200), SHELLS[1]: BASE - timedelta(days=180)})
    created.update({u: BASE - timedelta(days=250 + 23 * i) for i, u in enumerate(CASHOUTS)})
    types = {"feeder": "Savings", "mule": "Wallet", "collector": "Current",
             "shell": "Business", "cash-out": "Savings"}
    return [
        dict(account_uid=uid, customer_name=name, email=f"{uid.lower()}@demo.example",
             phone=f"90000{i:05d}", account_type=types[ROLES[uid]], created_at=created[uid],
             risk_level="Low", fraud_score=0.0, is_fraud=0, is_active=1)
        for i, (uid, name) in enumerate(zip(ROLES, NAMES))
    ]


def _transactions() -> list[tuple[str, dict]]:
    """Return (stage, transaction row) pairs in time order."""
    rows = []

    def add(stage, sender, receiver, amount, ts):
        rows.append((stage, dict(
            txn_uid=f"{PREFIX}TXN{len(rows) + 1:03d}", sender_uid=sender, receiver_uid=receiver,
            amount=float(amount), timestamp=ts, txn_type="transfer", status="normal",
            is_fraud=0, fraud_score=0.0,
        )))

    # 1) feeders -> mule within 25 minutes (one under Rs 50,000, so R3 skips it)
    feed_amounts = [52000, 61500, 48000, 75000, 83000, 57500, 66000, 90000, 71000]
    feed_minutes = [0, 3, 5, 8, 11, 14, 17, 21, 25]
    for uid, amt, m in zip(FEEDERS, feed_amounts, feed_minutes):
        add(STAGES[0], uid, MULE, amt, BASE + timedelta(minutes=m))

    # 2) mule forwards ~97% to the collector in one go
    add(STAGES[1], MULE, COLLECTOR, round(sum(feed_amounts) * 0.97, 2), BASE + timedelta(minutes=50))

    # 3) layering loop through two shell companies within 8 hours, under the R1 threshold
    add(STAGES[2], COLLECTOR, SHELLS[0], 92000, BASE + timedelta(hours=3))
    add(STAGES[2], SHELLS[0], SHELLS[1], 90500, BASE + timedelta(hours=5))
    add(STAGES[2], SHELLS[1], COLLECTOR, 89000, BASE + timedelta(hours=8))

    # 4) structured cash-out: 9 transfers just under the Rs 1,00,000 threshold in 8 minutes
    cash_amounts = [99500, 98200, 97800, 99000, 96500, 98900, 97200, 99300, 96800]
    for i, (uid, amt) in enumerate(zip(CASHOUTS, cash_amounts)):
        add(STAGES[3], COLLECTOR, uid, amt, BASE + timedelta(hours=26, minutes=i))
    return rows


def _random_time(rng: random.Random, start: datetime) -> datetime | None:
    """A random time between start and the end of 2024, away from the scenario."""
    span = (YEAR_END - start).total_seconds()
    for _ in range(100):
        if span <= 0:
            break
        ts = start + timedelta(seconds=rng.uniform(0, span))
        if not BASE - QUIET_BEFORE <= ts <= BASE + QUIET_AFTER:
            return ts
    return None


def _background(accounts: list[dict], real_created: dict[str, datetime]) -> list[dict]:
    """Ordinary customer activity for each demo account, mirroring
    data/generate_synthetic.plant_normal (lognormal amounts, random counterparties)."""
    rng = random.Random(42)
    real_uids = sorted(real_created)
    rows = []
    for acc in accounts:
        for _ in range(rng.randint(24, 36)):
            other = rng.choice(real_uids)
            # never date a transaction before either account was opened
            ts = _random_time(rng, max(acc["created_at"], real_created[other] or YEAR_START, YEAR_START))
            if ts is None:
                continue
            sender, receiver = ((acc["account_uid"], other) if rng.random() < 0.5
                                else (other, acc["account_uid"]))
            rows.append(dict(
                txn_uid=f"{PREFIX}BG{len(rows) + 1:04d}", sender_uid=sender, receiver_uid=receiver,
                amount=min(round(rng.lognormvariate(8.0, 1.0), 2), 95000.0), timestamp=ts,
                txn_type=rng.choice(["transfer", "payment", "withdrawal"]), status="normal",
                is_fraud=0, fraud_score=0.0,
            ))
    return rows


def _load_state() -> dict | None:
    if os.path.exists(STATE_JSON):
        with open(STATE_JSON) as fh:
            return json.load(fh)
    return None


def _save_state(db) -> None:
    os.makedirs(os.path.dirname(STATE_JSON), exist_ok=True)
    with open(STATE_JSON, "w") as fh:
        json.dump({"planted_at": datetime.now().isoformat(timespec="seconds"),
                   "max_alert_id": db.query(func.max(Alert.id)).scalar() or 0}, fh)


def remove_demo_data(db) -> dict:
    """Delete demo accounts and everything that references them, plus alerts
    raised since the demo was planted that nobody has worked on yet."""
    # The state file is only trusted while the demo is actually planted in this
    # database; after a re-seed its alert ids would point at unrelated alerts.
    state = _load_state() if db.query(Account.id).filter(_is_demo(Account.account_uid)).first() else None
    demo_alert = or_(_is_demo(Alert.account_uid), _is_demo(Alert.transaction_uid))
    demo_alert_uids = select(Alert.alert_uid).where(demo_alert)
    touches_demo = or_(_is_demo(Transaction.txn_uid), _is_demo(Transaction.sender_uid),
                       _is_demo(Transaction.receiver_uid))
    removed = {
        # cases on demo accounts, or on an alert about a demo transaction (which
        # can name a real account) - deleting the alert alone would orphan the case
        "cases": db.query(Case).filter(or_(_is_demo(Case.account_uid), Case.alert_uid.in_(demo_alert_uids)))
                   .delete(synchronize_session=False),
        "alerts": db.query(Alert).filter(demo_alert).delete(synchronize_session=False),
    }

    kept = 0
    if state:
        since_plant = Alert.id > state["max_alert_id"]
        in_a_case = Alert.alert_uid.in_(select(Case.alert_uid).where(Case.alert_uid.isnot(None)))
        removed["alerts"] += (db.query(Alert).filter(since_plant, Alert.status == "Pending", ~in_a_case)
                                .delete(synchronize_session=False))
        kept = db.query(Alert).filter(since_plant).count()

    removed |= {
        "rule_hits": db.query(RuleHit)
                       .filter(RuleHit.txn_uid.in_(select(Transaction.txn_uid).where(touches_demo)))
                       .delete(synchronize_session=False),
        "graph_metrics": db.query(GraphMetric).filter(_is_demo(GraphMetric.account_uid))
                           .delete(synchronize_session=False),
        "transactions": db.query(Transaction).filter(touches_demo).delete(synchronize_session=False),
        "accounts": db.query(Account).filter(_is_demo(Account.account_uid)).delete(synchronize_session=False),
    }
    db.commit()
    if os.path.exists(STATE_JSON):
        os.remove(STATE_JSON)
    if kept:
        print(f"Kept {kept} alerts raised since the demo was planted: someone has worked on them.")
    return removed


def plant(db) -> None:
    real_created = dict(db.query(Account.account_uid, Account.created_at)
                          .filter(~_is_demo(Account.account_uid)))
    if not real_created:
        raise SystemExit("No base dataset found. Seed it first:\n"
                         "  python -m data.generate_synthetic\n  python -m scripts.seed_data")
    removed = remove_demo_data(db)
    if any(removed.values()):
        print("Removed previous demo data: " + ", ".join(f"{n} {k}" for k, n in removed.items() if n))
    accounts, txns = _accounts(), _transactions()
    background = _background(accounts, real_created)
    db.bulk_insert_mappings(Account, accounts)
    db.bulk_insert_mappings(Transaction, [row for _, row in txns] + background)
    db.commit()
    _save_state(db)
    print(f"Planted {len(accounts)} accounts, {len(txns)} scenario transactions and "
          f"{len(background)} ordinary background transactions (ids start with {PREFIX}).")
    for stage in STAGES:
        stage_rows = [row for s, row in txns if s == stage]
        total = sum(r["amount"] for r in stage_rows)
        print(f"  {stage:16s} {len(stage_rows):2d} txns  Rs {total:>12,.0f}")


def run_pipeline(db, generate_alerts: bool = True) -> dict:
    """Run the same steps as the UI, in the sidebar's order (GNN skipped)."""
    steps = [
        ("Rule Detection", rules_engine.apply_rules,
         lambda r: f"{r['total_suspicious']} suspicious transactions"),
        ("Graph Analysis", graph_analysis.analyze,
         lambda r: f"{r['nodes']} accounts, {r['edges']} edges, {r['cycles_found']} short cycles"),
        ("Features", features.build_and_save,
         lambda r: f"{r['accounts']} accounts x {r['features']} features"),
        ("ML Scoring", baseline.train_and_score,
         lambda r: f"best model {r['best_model']}, test F1 {r['results'][r['best_model']]['f1']}"),
        ("Fraud Alerts", lambda s: alert_engine.generate(s, ml_threshold=ML_ALERT_THRESHOLD),
         lambda r: f"+{r['created_rule_alerts']} rule alerts, +{r['created_ml_alerts']} ML alerts"),
        ("Fraud Rings", fraud_ring.detect,
         lambda r: f"{r['rings_found']} rings, {r['accounts_involved']} accounts"),
    ]
    results = {}
    for name, fn, describe in steps:
        if name == "Fraud Alerts" and not generate_alerts:
            continue
        start = time.perf_counter()
        results[name] = fn(db)
        print(f"  {name:15s} {time.perf_counter() - start:6.1f}s  {describe(results[name])}")
    return results


def report(db, rings: dict) -> None:
    status = dict(db.query(Transaction.txn_uid, Transaction.status)
                    .filter(_is_demo(Transaction.txn_uid)))
    rule_hits = defaultdict(set)
    for txn_uid, rule in db.query(RuleHit.txn_uid, RuleHit.rule).filter(_is_demo(RuleHit.txn_uid)):
        rule_hits[txn_uid].add(rule)
    stage_of = {row["txn_uid"]: stage for stage, row in _transactions()}

    print("\nRule engine - did each stage get caught?")
    for stage in STAGES:
        uids = [u for u, s in stage_of.items() if s == stage]
        flagged = sum(status.get(u) == "suspicious" for u in uids)
        fired = Counter(rule for u in uids for rule in rule_hits[u])
        rules_text = ", ".join(f"{RULE_SHORT[r]} x{n}" for r, n in sorted(fired.items())) or "none"
        print(f"  {stage:16s} flagged {flagged}/{len(uids)}   {rules_text}")

    accounts = (db.query(Account.account_uid, Account.risk_level, Account.fraud_score)
                  .filter(_is_demo(Account.account_uid)).all())
    alert_counts = defaultdict(int)
    for (uid,) in db.query(Alert.account_uid).filter(_is_demo(Alert.account_uid)):
        alert_counts[uid] += 1
    # member_ids is the full membership; ring["nodes"] is capped at 40 for display
    ring_of = {uid: ring for ring in rings.get("rings", []) for uid in ring.get("member_ids", [])}

    print("\nAccounts - rules risk level, ML score (model was told they are legit), alerts, ring")
    print(f"  {'account':16s} {'role':10s} {'risk':7s} {'ML score':>8s} {'alerts':>6s}  ring")
    for uid, risk, score in sorted(accounts, key=lambda a: list(ROLES).index(a.account_uid)):
        ring = ring_of.get(uid)
        print(f"  {uid:16s} {ROLES[uid]:10s} {risk:7s} {score or 0:8.3f} {alert_counts[uid]:6d}  "
              f"{ring['ring_id'] if ring else '-'}")

    demo_rings = {ring["ring_id"]: ring for uid, ring in ring_of.items() if uid.startswith(PREFIX)}
    print("\nFraud rings containing demo accounts:")
    if not demo_rings:
        print("  none")
    for ring in demo_rings.values():
        print(f"  {ring['ring_id']}: {ring['size']} accounts, main {ring['main_account']}, "
              f"withdrawal {ring['withdrawal_account'] or '-'}, Rs {ring['total_flow']:,.0f} moved, "
              f"risk {ring['risk']} (ML score {ring['avg_fraud_score']:.2f}, "
              f"rules fired: {' '.join(ring['rules']) or 'none'})")


def cleanup(db) -> None:
    removed = remove_demo_data(db)
    print("Removed " + ", ".join(f"{n} {k}" for k, n in removed.items()) + ".")
    if os.path.exists(features.FEATURES_CSV) or os.path.exists(fraud_ring.RINGS_JSON):
        print("\nRe-running the pipeline without the demo (alert generation skipped):")
        run_pipeline(db, generate_alerts=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plant-only", action="store_true",
                       help="plant the scenario but leave the pipeline to the UI")
    group.add_argument("--cleanup", action="store_true",
                       help="remove all demo data, then refresh scores, features and rings")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.cleanup:
            cleanup(db)
            return
        plant(db)
        if args.plant_only:
            print("\nNow log in and run, in the sidebar's order: Rule Detection -> Graph Analysis -> "
                  "Features -> ML Scoring -> Fraud Alerts -> Fraud Rings.\nThen search for "
                  f"{PREFIX} on the Accounts, Alerts and Fraud Rings pages.")
            return
        print("\nRunning the detection pipeline:")
        results = run_pipeline(db)
        report(db, results["Fraud Rings"])
        print(f"\nIn the UI: search for {PREFIX} on Accounts / Alerts, or open the ring on Fraud Rings.")
        print("Remove the demo again with: python -m scripts.demo_scenario --cleanup")
    finally:
        db.close()


if __name__ == "__main__":
    main()

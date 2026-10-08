"""Plant the demo scenario into a copy and run the detection pipeline on it.

The heavy half of scripts/demo_scenario.py, which describes the scenario and
is what you run. Import it only after scripts.demo_common.point_app_at(DEMO_DIR):
it uses the app's database engine, which must already point at the copy.
"""
import random
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import and_

from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401  (registers tables)
from app.ml import alerts as alert_engine
from app.ml import baseline, features, fraud_ring, graph_analysis
from app.ml import rules as rules_engine
from app.models.account import Account
from app.models.alert import Alert
from app.models.rule_hit import RuleHit
from app.models.transaction import Transaction
from scripts.demo_common import DEMO_DIR, PREFIX, PREFIX_END, check_pointed_at

BASE = datetime(2024, 11, 14, 1, 30)   # a night inside the synthetic data's 2024 range
ML_ALERT_THRESHOLD = 0.8               # same default as the Fraud Alerts page
YEAR_START, YEAR_END = datetime(2024, 1, 1), datetime(2024, 12, 31, 23, 59)
QUIET_BEFORE, QUIET_AFTER = timedelta(days=1), timedelta(days=2)  # no background txns near the scenario

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
RULE_LABEL = {rules_engine.RULE_CODES[name]: label                   # "R4" -> "R4 · Many senders → one account"
              for name, label in rules_engine.RULE_LABELS.items()}


def _is_demo(column):
    return and_(column >= PREFIX, column < PREFIX_END)   # see PREFIX_END


# --------------------------------------------------------------- scenario data

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
    if span <= 0:
        return None
    for _ in range(100):
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


# ---------------------------------------------------------- plant and report

def plant(db) -> None:
    real_created = dict(db.query(Account.account_uid, Account.created_at))
    if not real_created:
        raise SystemExit("No base dataset found. Seed it first:\n"
                         "  python -m data.generate_synthetic\n  python -m scripts.seed_data")
    accounts, txns = _accounts(), _transactions()
    background = _background(accounts, real_created)
    db.bulk_insert_mappings(Account, accounts)
    db.bulk_insert_mappings(Transaction, [row for _, row in txns] + background)
    db.commit()
    print(f"Planted {len(accounts)} accounts, {len(txns)} scenario transactions and "
          f"{len(background)} ordinary background transactions into the copy "
          f"(ids start with {PREFIX}).")
    for stage in STAGES:
        stage_rows = [row for s, row in txns if s == stage]
        total = sum(r["amount"] for r in stage_rows)
        print(f"  {stage:16s} {len(stage_rows):2d} txns  Rs {total:>12,.0f}")


def run_pipeline(db) -> dict:
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
        start = time.perf_counter()
        results[name] = fn(db)
        print(f"  {name:15s} {time.perf_counter() - start:6.1f}s  {describe(results[name])}")
    return results


def report(db, rings: dict) -> None:
    status = dict(db.query(Transaction.txn_uid, Transaction.status)
                    .filter(_is_demo(Transaction.txn_uid)))
    rule_hits = defaultdict(set)
    for txn_uid, rule in db.query(RuleHit.txn_uid, RuleHit.rule).filter(_is_demo(RuleHit.txn_uid)):
        rule_hits[txn_uid].add(rules_engine.RULE_CODES[rule])
    stage_of = {row["txn_uid"]: stage for stage, row in _transactions()}

    print("\nRule engine - did each stage get caught?")
    for stage in STAGES:
        uids = [u for u, s in stage_of.items() if s == stage]
        flagged = sum(status.get(u) == "suspicious" for u in uids)
        fired = Counter(code for u in uids for code in rule_hits[u])
        rules_text = ", ".join(f"{RULE_LABEL[c]} x{n}" for c, n in sorted(fired.items())) or "none"
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
              f"risk {ring['risk']} (ML score {ring['avg_fraud_score']:.2f})")
        print(f"    rules fired on its transactions: "
              f"{', '.join(RULE_LABEL[c] for c in ring['rules']) or 'none'}")


def run(plant_only: bool) -> None:
    """Plant into the demo copy and, unless plant_only, run the pipeline and report."""
    check_pointed_at(DEMO_DIR, engine)   # never the real database or pipeline outputs
    Base.metadata.create_all(bind=engine)   # the copy may predate newer tables
    db = SessionLocal()
    try:
        plant(db)
        if not plant_only:
            print("\nRunning the detection pipeline on the copy:")
            results = run_pipeline(db)
            report(db, results["Fraud Rings"])
    finally:
        db.close()

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
    python -m scripts.demo_scenario --cleanup     # put everything back

Planting first snapshots the SQLite database, saved_models/ and features.csv
into data/demo_snapshot/. --cleanup restores that snapshot exactly - scores,
alerts, rings and GNN results included - so anything else changed after
planting is rolled back too. Re-planting restores the snapshot before planting
again. Without a snapshot (e.g. planted by an older version of this script),
--cleanup can only delete the DEMO- rows; re-run the pipeline afterwards.
"""
import argparse
import json
import os
import random
import shutil
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select

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

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(BACKEND_DIR, "data", "demo_snapshot")   # gitignored
SNAPSHOT_DB = os.path.join(SNAPSHOT_DIR, "database.sqlite")
SNAPSHOT_MODELS = os.path.join(SNAPSHOT_DIR, "saved_models")
SNAPSHOT_FEATURES = os.path.join(SNAPSHOT_DIR, "features.csv")
SNAPSHOT_META = os.path.join(SNAPSHOT_DIR, "snapshot.json")         # written last: marks it complete

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

# ASCII rule names (the app's RULE_LABELS use symbols some Windows consoles can't print)
RULE_NAMES = {
    "large_amount": "large amount", "rapid_transactions": "rapid", "new_account_large": "new account",
    "fan_in": "fan-in", "fan_out": "fan-out", "circular": "circular",
}
RULE_LABEL = {rules_engine.RULE_CODES[r]: f"{rules_engine.RULE_CODES[r]} {name}"
              for r, name in RULE_NAMES.items()}                              # "R4" -> "R4 fan-in"


def _is_demo(column):
    # Case-sensitive prefix match that can still use the uid indexes. Not
    # LIKE 'DEMO-%': SQLite's LIKE ignores case, so it would also match (and
    # delete) a real account named "demo-...". '.' is the character after '-'.
    return and_(column >= PREFIX, column < PREFIX[:-1] + ".")


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


# ------------------------------------------------------------ snapshot/restore

def _database_file() -> str:
    if engine.url.get_backend_name() != "sqlite":
        raise SystemExit("The demo snapshots the database file, so it only supports SQLite "
                         f"(DATABASE_URL is {engine.url.get_backend_name()}).")
    return os.path.normcase(os.path.abspath(engine.url.database))


def _sqlite_copy(src_path: str, dst_path: str) -> None:
    """Page-level copy with SQLite's backup API: safe while the dev server has
    the database open, and an interrupted copy leaves the destination unchanged.
    Callers must close their Session first - the copy waits on any open lock."""
    engine.dispose()   # release this script's own pooled connections first
    src, dst = sqlite3.connect(src_path), sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def _load_snapshot() -> dict | None:
    """The snapshot's metadata, or None if there is no complete, readable snapshot."""
    try:
        with open(SNAPSHOT_META) as fh:
            meta = json.load(fh)
        return meta if {"database", "taken_at"} <= meta.keys() else None
    except (OSError, ValueError):
        return None


def _take_snapshot() -> None:
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)        # drop any incomplete leftovers
    os.makedirs(SNAPSHOT_MODELS)
    _sqlite_copy(_database_file(), SNAPSHOT_DB)
    if os.path.isdir(fraud_ring.SAVED_DIR):
        for name in os.listdir(fraud_ring.SAVED_DIR):
            path = os.path.join(fraud_ring.SAVED_DIR, name)
            if os.path.isfile(path):
                shutil.copy2(path, SNAPSHOT_MODELS)
    has_features = os.path.exists(features.FEATURES_CSV)
    if has_features:
        shutil.copy2(features.FEATURES_CSV, SNAPSHOT_FEATURES)
    meta = {"database": _database_file(), "taken_at": datetime.now().isoformat(timespec="seconds"),
            "has_features": has_features}
    with open(SNAPSHOT_META + ".tmp", "w") as fh:
        json.dump(meta, fh)
    os.replace(SNAPSHOT_META + ".tmp", SNAPSHOT_META)   # atomic: the snapshot now counts as complete


def _restore_snapshot(meta: dict) -> None:
    """Put the pipeline outputs, then the database, back exactly as snapshotted.
    The database goes last: until it is restored the demo still shows as planted,
    so an interrupted restore is simply repeated on the next run."""
    os.makedirs(fraud_ring.SAVED_DIR, exist_ok=True)
    for name in os.listdir(fraud_ring.SAVED_DIR):
        path = os.path.join(fraud_ring.SAVED_DIR, name)
        if os.path.isfile(path):
            os.remove(path)
    for name in os.listdir(SNAPSHOT_MODELS):
        shutil.copy2(os.path.join(SNAPSHOT_MODELS, name), fraud_ring.SAVED_DIR)
    if meta.get("has_features"):
        shutil.copy2(SNAPSHOT_FEATURES, features.FEATURES_CSV)
    elif os.path.exists(features.FEATURES_CSV):
        os.remove(features.FEATURES_CSV)
    _sqlite_copy(SNAPSHOT_DB, _database_file())


def _demo_planted(db) -> bool:
    return db.query(Account.id).filter(_is_demo(Account.account_uid)).first() is not None


def remove_demo_rows(db) -> dict:
    """Fallback when there is no snapshot: delete demo accounts and every row
    that references them. Scores, features and rings keep the demo's influence
    until the pipeline is re-run."""
    demo_alert = or_(_is_demo(Alert.account_uid), _is_demo(Alert.transaction_uid))
    touches_demo = or_(_is_demo(Transaction.txn_uid), _is_demo(Transaction.sender_uid),
                       _is_demo(Transaction.receiver_uid))
    removed = {
        # cases on demo accounts, or on an alert about a demo transaction (which
        # can name a real account) - deleting the alert alone would orphan the case
        "cases": db.query(Case).filter(or_(_is_demo(Case.account_uid),
                                           Case.alert_uid.in_(select(Alert.alert_uid).where(demo_alert))))
                   .delete(synchronize_session=False),
        "alerts": db.query(Alert).filter(demo_alert).delete(synchronize_session=False),
        "rule_hits": db.query(RuleHit)
                       .filter(RuleHit.txn_uid.in_(select(Transaction.txn_uid).where(touches_demo)))
                       .delete(synchronize_session=False),
        "graph_metrics": db.query(GraphMetric).filter(_is_demo(GraphMetric.account_uid))
                           .delete(synchronize_session=False),
        "transactions": db.query(Transaction).filter(touches_demo).delete(synchronize_session=False),
        "accounts": db.query(Account).filter(_is_demo(Account.account_uid)).delete(synchronize_session=False),
    }
    db.commit()
    return removed


def _snapshot_for_this_database() -> dict | None:
    """The snapshot, if it exists and was taken of the database in use."""
    meta = _load_snapshot()
    if meta and meta["database"] != _database_file():
        raise SystemExit(f"{SNAPSHOT_DIR} holds a demo snapshot of a different database "
                         f"({meta['database']}). Run --cleanup with that database first, "
                         "or delete the folder if you no longer need it.")
    return meta


# ---------------------------------------------------------------- the commands

def plant(db) -> None:
    _database_file()   # fail early on non-SQLite
    if not db.query(Account.id).filter(~_is_demo(Account.account_uid)).first():
        raise SystemExit("No base dataset found. Seed it first:\n"
                         "  python -m data.generate_synthetic\n  python -m scripts.seed_data")
    snapshot = _snapshot_for_this_database()
    planted = _demo_planted(db)
    if planted and not snapshot:   # planted without a snapshot, e.g. by an older version
        removed = remove_demo_rows(db)
        print("Removed old demo rows: " + ", ".join(f"{n} {k}" for k, n in removed.items() if n))
    db.close()   # end this session's transaction: the SQLite backup waits on any open lock
    if snapshot and planted:
        _restore_snapshot(snapshot)
        print(f"Restored the pre-demo state from {snapshot['taken_at']} before planting again.")
    else:
        _take_snapshot()           # (a snapshot without a planted demo is stale: replace it)

    real_created = dict(db.query(Account.account_uid, Account.created_at)
                          .filter(~_is_demo(Account.account_uid)))
    accounts, txns = _accounts(), _transactions()
    background = _background(accounts, real_created)
    db.bulk_insert_mappings(Account, accounts)
    db.bulk_insert_mappings(Transaction, [row for _, row in txns] + background)
    db.commit()
    print(f"Planted {len(accounts)} accounts, {len(txns)} scenario transactions and "
          f"{len(background)} ordinary background transactions (ids start with {PREFIX}).")
    for stage in STAGES:
        stage_rows = [row for s, row in txns if s == stage]
        total = sum(r["amount"] for r in stage_rows)
        print(f"  {stage:16s} {len(stage_rows):2d} txns  Rs {total:>12,.0f}")


def cleanup(db) -> None:
    snapshot = _snapshot_for_this_database()
    planted = _demo_planted(db)
    if snapshot and planted:
        db.close()   # end this session's transaction: the SQLite backup waits on any open lock
        _restore_snapshot(snapshot)
        print(f"Restored the database, saved_models/ and features.csv to how they were at "
              f"{snapshot['taken_at']}, when the demo was planted. Anything else changed since "
              "then was rolled back too.")
    elif planted:
        removed = remove_demo_rows(db)
        print("No snapshot found, so only the demo rows were removed: "
              + ", ".join(f"{n} {k}" for k, n in removed.items()) + ".")
        print("Scores, features and rings may still reflect the demo - re-run the pipeline from the UI.")
    else:
        print("The demo isn't planted in this database; nothing to remove.")
    shutil.rmtree(SNAPSHOT_DIR, ignore_errors=True)


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


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plant-only", action="store_true",
                       help="plant the scenario but leave the pipeline to the UI")
    group.add_argument("--cleanup", action="store_true",
                       help="restore the snapshot taken when the demo was planted")
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
        print("Put everything back with: python -m scripts.demo_scenario --cleanup")
    finally:
        db.close()


if __name__ == "__main__":
    main()

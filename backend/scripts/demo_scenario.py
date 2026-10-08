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

Your own data is never changed. The demo works on a copy in data/demo/: your
database, saved_models/ and features.csv are copied there, the scenario is
planted into the copy, and the pipeline writes its outputs there too.

Run from the backend/ folder, after init_db + seed_data:
    python -m scripts.demo_scenario               # copy, plant, run the pipeline, report
    python -m scripts.demo_scenario --plant-only  # copy and plant; run the pipeline from the UI
    python -m scripts.demo_scenario --serve       # run the backend on the copy, for the UI
    python -m scripts.demo_scenario --cleanup     # delete the copy

--serve uses port 8000 like the normal backend (so the frontend needs no
changes): stop the normal backend first. Planting again starts over from a
fresh copy of your current data.
"""
import argparse
import os
import random
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import and_
from sqlalchemy.engine import make_url

from app.config import BACKEND_DIR, settings
from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401  (registers tables)
from app.ml import alerts as alert_engine
from app.ml import baseline, features, fraud_ring, graph_analysis
from app.ml import rules as rules_engine
from app.models.account import Account
from app.models.alert import Alert
from app.models.rule_hit import RuleHit
from app.models.transaction import Transaction

PREFIX = "DEMO-"
BASE = datetime(2024, 11, 14, 1, 30)   # a night inside the synthetic data's 2024 range
ML_ALERT_THRESHOLD = 0.8               # same default as the Fraud Alerts page
YEAR_START, YEAR_END = datetime(2024, 1, 1), datetime(2024, 12, 31, 23, 59)
QUIET_BEFORE, QUIET_AFTER = timedelta(days=1), timedelta(days=2)  # no background txns near the scenario

# The copy: a database plus OUTPUT_DIR for the pipeline's files (see app/config.py)
DEMO_DIR = os.path.join(BACKEND_DIR, "data", "demo")   # gitignored
DEMO_DB = os.path.join(DEMO_DIR, "fraud_detection.db")
DEMO_SETTINGS = settings.model_copy(update={"DATABASE_URL": "sqlite:///" + Path(DEMO_DB).as_posix(),
                                            "OUTPUT_DIR": DEMO_DIR})
ON_COPY_FLAG = "DEMO_SCENARIO_ON_COPY"   # set for the child process that plants into the copy
DEMO_PORT = 8000                         # where the frontend's VITE_API_URL points
COPY_TIMEOUT = 60                        # seconds to wait for a locked database
LEGACY_STATE = os.path.join(settings.saved_models_dir, "demo_state.json")  # written by an older version

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
    # Case-sensitive prefix match that can still use the uid indexes. Not
    # LIKE 'DEMO-%': SQLite's LIKE ignores case, so it would also match a real
    # account named "demo-...". The upper bound is the prefix with its last
    # character bumped by one ("DEMO." for "DEMO-").
    return and_(column >= PREFIX, column < PREFIX[:-1] + chr(ord(PREFIX[-1]) + 1))


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


# ------------------------------------------------------------------- the copy

def _source_database() -> str:
    url = make_url(settings.DATABASE_URL)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        raise SystemExit("The demo copies the database file, so it needs a SQLite DATABASE_URL "
                         f"(this one is {url.get_backend_name()}).")
    path = os.path.abspath(url.database)
    if not os.path.isfile(path):
        raise SystemExit(f"No database at {path}. Set it up first:\n  python -m scripts.init_db\n"
                         "  python -m data.generate_synthetic\n  python -m scripts.seed_data")
    if os.path.normcase(path).startswith(os.path.normcase(DEMO_DIR + os.sep)):
        raise SystemExit(f"DATABASE_URL points into {DEMO_DIR}, the demo copy itself. Unset it first.")
    return path


def _sqlite_copy(source: str, target: str) -> None:
    """Copy a SQLite database with its backup API, which is consistent even
    while the dev server is using it. The source is opened read-only: it is
    never changed, and a missing file is an error rather than a new empty one."""
    deadline = time.monotonic() + COPY_TIMEOUT

    def give_up_when_stuck(status, remaining, total):
        if time.monotonic() > deadline:   # backup() itself retries a locked database forever
            raise TimeoutError

    src = sqlite3.connect(Path(source).as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst, progress=give_up_when_stuck)
    except TimeoutError:
        raise SystemExit(f"{source} stayed locked for over {COPY_TIMEOUT}s. Is a pipeline step running "
                         "in the app? Try again when it finishes.") from None
    finally:
        src.close()
        dst.close()


def _delete_copy() -> bool:
    if not os.path.exists(DEMO_DIR):
        return False
    try:
        shutil.rmtree(DEMO_DIR)
    except OSError as exc:
        raise SystemExit(f"Couldn't delete {DEMO_DIR}: {exc.strerror}. If the demo backend "
                         "(--serve) is running, stop it and try again.") from None
    return True


def make_copy() -> None:
    """Fresh copy of the database and pipeline outputs into DEMO_DIR. Only
    reads from the originals."""
    source = _source_database()
    _delete_copy()
    os.makedirs(DEMO_SETTINGS.saved_models_dir)
    os.makedirs(DEMO_SETTINGS.processed_dir)
    _sqlite_copy(source, DEMO_DB)
    if os.path.isdir(settings.saved_models_dir):
        for name in os.listdir(settings.saved_models_dir):
            path = os.path.join(settings.saved_models_dir, name)
            if os.path.isfile(path):
                shutil.copy2(path, DEMO_SETTINGS.saved_models_dir)
    if os.path.isfile(features.FEATURES_CSV):
        shutil.copy2(features.FEATURES_CSV, DEMO_SETTINGS.processed_dir)
    print(f"Copied your database and pipeline outputs into {DEMO_DIR}", flush=True)  # before the child prints


def _demo_env() -> dict:
    """Environment that points the app at the copy (env vars beat .env)."""
    return {**os.environ, "DATABASE_URL": DEMO_SETTINGS.DATABASE_URL, "OUTPUT_DIR": DEMO_DIR}


# ---------------------------------------------------------------- the commands

def plant(db) -> None:
    if db.query(Account.id).filter(_is_demo(Account.account_uid)).first():
        raise SystemExit(
            "Your database already has DEMO- accounts, planted into it by an older version of "
            "this script. To remove them, rebuild it: delete fraud_detection.db, then run "
            "python -m scripts.init_db and python -m scripts.seed_data.")
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


def plant_and_run(plant_only: bool) -> None:
    """Runs in the child process, where the whole app is pointed at the copy."""
    if settings.DATABASE_URL != DEMO_SETTINGS.DATABASE_URL:   # never plant into the real database
        raise SystemExit(f"{ON_COPY_FLAG} is set but DATABASE_URL isn't the demo copy.")
    Base.metadata.create_all(bind=engine)   # the copy may predate newer tables
    db = SessionLocal()
    try:
        plant(db)
        if plant_only:
            print("\nNow stop your normal backend, start the demo one with\n"
                  "  python -m scripts.demo_scenario --serve\nthen log in and run, in the "
                  "sidebar's order: Rule Detection -> Graph Analysis -> Features -> ML Scoring "
                  f"-> Fraud Alerts -> Fraud Rings.\nThen search for {PREFIX} on the Accounts, "
                  "Alerts and Fraud Rings pages.")
            return
        print("\nRunning the detection pipeline on the copy:")
        results = run_pipeline(db)
        report(db, results["Fraud Rings"])
        print("\nTo show it in the UI, stop your normal backend and run\n"
              "  python -m scripts.demo_scenario --serve\n"
              f"then search for {PREFIX} on Accounts / Alerts, or open the ring on Fraud Rings.")
        print("Your own database and pipeline outputs were not changed. "
              "Delete the copy with --cleanup.")
    finally:
        db.close()


def serve() -> None:
    if not os.path.isfile(DEMO_DB):
        raise SystemExit("There's no demo copy yet. Make one first: python -m scripts.demo_scenario")
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", DEMO_PORT))
        except OSError:
            raise SystemExit(f"Port {DEMO_PORT} is in use. Stop your normal backend "
                             "(Ctrl+C in its terminal) and try again.") from None
    print(f"Serving the demo copy on http://127.0.0.1:{DEMO_PORT} - use the frontend as usual. "
          "Ctrl+C to stop.")
    try:
        subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(DEMO_PORT)],
                        env=_demo_env())
    except KeyboardInterrupt:
        pass


def cleanup() -> None:
    removed = _delete_copy()
    if os.path.isfile(LEGACY_STATE):
        os.remove(LEGACY_STATE)
    print(f"Deleted the demo copy ({DEMO_DIR})." if removed else "There's no demo copy to delete.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # rule labels use symbols cp1252 lacks (when output is redirected)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plant-only", action="store_true",
                       help="plant the scenario but leave the pipeline to the UI")
    group.add_argument("--serve", action="store_true",
                       help="run the backend on the demo copy (stop the normal one first)")
    group.add_argument("--cleanup", action="store_true", help="delete the demo copy")
    args = parser.parse_args()

    if args.cleanup:
        cleanup()
    elif args.serve:
        serve()
    elif os.environ.get(ON_COPY_FLAG):
        plant_and_run(args.plant_only)
    else:
        make_copy()
        # The app reads DATABASE_URL and OUTPUT_DIR once, when it is imported, so
        # planting and the pipeline run in a fresh process that sees only the copy.
        sys.exit(subprocess.call([sys.executable, "-m", "scripts.demo_scenario", *sys.argv[1:]],
                                 env={**_demo_env(), ON_COPY_FLAG: "1"}))


if __name__ == "__main__":
    main()

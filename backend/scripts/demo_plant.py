"""Plant the demo scenario and run the detection pipeline on it - into a copy of
the real data (with ordinary background activity), or into the standalone demo
database (the 22 scripted accounts and transactions, nothing else).

The heavy half of scripts/demo_scenario.py, which is what you run. Import it
only after scripts.demo_common.point_app_at(): it uses the app's database
engine, which must already point at the demo database. The scenario itself
is defined in app/demo/scenario.py.
"""
import random
import time
from datetime import datetime, timedelta


from app.database import SessionLocal, engine
from app.demo import coverage
from app.demo.scenario import (  # noqa: F401  (the scenario data, shared with the app)
    BACKGROUND_PREFIX, BASE, CASHOUTS, COLLECTOR, FEEDERS, MULE, NAMES, ROLES, SHELLS, STAGES,
    scenario_accounts as _accounts, scenario_transactions as _transactions,
)
from app.migrations import run_migrations
from app import models  # noqa: F401  (registers tables)
from app.ml import alerts as alert_engine
from app.ml import baseline, features, fraud_ring, graph_analysis
from app.ml import rules as rules_engine
from app.models.account import Account
from app.models.transaction import Transaction
from scripts.demo_common import DEMO_DIR, PREFIX, STANDALONE_DIR, check_pointed_at

ML_ALERT_THRESHOLD = 0.8               # same default as the Fraud Alerts page
YEAR_START, YEAR_END = datetime(2024, 1, 1), datetime(2024, 12, 31, 23, 59)
QUIET_BEFORE, QUIET_AFTER = timedelta(days=1), timedelta(days=2)  # no background txns near the scenario

# --------------------------------------------------------- background activity

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
                txn_uid=f"{BACKGROUND_PREFIX}{len(rows) + 1:04d}", sender_uid=sender, receiver_uid=receiver,
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
    _print_stages(txns)


def _print_stages(txns) -> None:
    for stage in STAGES:
        stage_rows = [row for s, row in txns if s == stage]
        total = sum(r["amount"] for r in stage_rows)
        print(f"  {stage:16s} {len(stage_rows):2d} txns  Rs {total:>12,.0f}")


def run_pipeline(db, with_ml: bool = True) -> dict:
    """Run the same steps as the UI, in the sidebar's order (GNN skipped; ML
    skipped too without with_ml)."""
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
    if not with_ml:
        steps = [step for step in steps if step[0] != "ML Scoring"]
    results = {}
    for name, fn, describe in steps:
        start = time.perf_counter()
        results[name] = fn(db)
        print(f"  {name:15s} {time.perf_counter() - start:6.1f}s  {describe(results[name])}")
    return results


def report(db, ml: bool = True) -> None:
    """Print what caught each stage, each account and the rings holding the
    scenario - from the same coverage report the Demo Scenario page shows.
    ml: whether ML scoring ran, so there are model scores to show."""
    data = coverage.report(db)
    labels = data["rule_labels"]
    print("\nRule engine - did each stage get caught?")
    for stage in data["stages"]:
        fired = ", ".join(f"{labels[code]} x{n}" for code, n in stage["rules_fired"].items()) or "none"
        missing = [code for code in stage["expected_rules"] if code not in stage["rules_fired"]]
        print(f"  {stage['stage']:16s} flagged {stage['flagged']}/{stage['total']}   {fired}"
              + (f"   (designed to trigger {', '.join(missing)}: did not fire)" if missing else ""))

    if ml:
        print("\nAccounts - rules risk level, ML score (model was told they are legit), alerts, ring")
        print(f"  {'account':16s} {'role':10s} {'risk':7s} {'ML score':>8s} {'alerts':>6s}  ring")
    else:
        print("\nAccounts - role, risk level the rules raised, alerts, ring")
        print(f"  {'account':16s} {'role':10s} {'risk':7s} {'alerts':>6s}  ring")
    for acc in data["accounts"]:
        score = f" {acc['fraud_score'] or 0:8.3f}" if ml else ""
        print(f"  {acc['account_uid']:16s} {acc['role']:10s} {acc['risk_level'] or '-':7s}{score} "
              f"{acc['alerts']:6d}  {acc['ring_id'] or '-'}")

    print("\nFraud rings containing demo accounts:")
    if not data["rings"]:
        print("  none")
    for ring in data["rings"]:
        score = f" (ML score {ring['avg_fraud_score']:.2f})" if ml and ring["avg_fraud_score"] is not None else ""
        print(f"  {ring['ring_id']}: {ring['size']} accounts, main {ring['main_account']}, "
              f"withdrawal {ring['withdrawal_account'] or '-'}, Rs {ring['total_flow']:,.0f} moved, "
              f"risk {ring['risk']}{score}")
        print(f"    rules fired on its transactions: {', '.join(labels[c] for c in ring['rules']) or 'none'}")

    cov = data["coverage"]
    print(f"\nCoverage: {cov['transactions_flagged']}/{cov['transactions_total']} transactions flagged, "
          f"{cov['stages_detected']}/{cov['stages_total']} stages detected, rules fired: "
          f"{' '.join(cov['rules_fired']) or 'none'}, {cov['accounts_in_rings']}/{cov['accounts_total']} "
          "accounts in a fraud ring.")


def run(plant_only: bool, folder: str = DEMO_DIR) -> None:
    """Plant into the demo copy in folder and, unless plant_only, run the pipeline and report."""
    check_pointed_at(folder, engine)   # never the real database or pipeline outputs
    run_migrations(engine)   # the copy may predate newer tables and columns
    db = SessionLocal()
    try:
        plant(db)
        if not plant_only:
            print("\nRunning the detection pipeline on the copy:")
            run_pipeline(db)
            report(db)
    finally:
        db.close()


# ------------------------------------------------------------- standalone demo

def plant_standalone(db) -> None:
    """Only the scripted scenario: its 22 accounts and 22 transactions, into an
    empty database - no copied data and no background activity."""
    if db.query(Account.id).first() is not None or db.query(Transaction.id).first() is not None:
        raise SystemExit("The standalone demo database isn't empty; it should have just been created. "
                         "Delete it with --cleanup --standalone and build it again.")
    accounts, txns = _accounts(), _transactions()
    db.bulk_insert_mappings(Account, accounts)
    db.bulk_insert_mappings(Transaction, [row for _, row in txns])
    db.commit()
    print(f"Planted the scenario alone: {len(accounts)} accounts and {len(txns)} transactions "
          f"(ids start with {PREFIX}), nothing else.")
    _print_stages(txns)


def run_standalone(plant_only: bool, folder: str = STANDALONE_DIR) -> None:
    """Build the standalone demo database in folder: every table, the admin user,
    the scenario and, unless plant_only, the detection steps that make sense on
    22 scripted accounts (no ML or GNN training: that needs the main labelled dataset)."""
    check_pointed_at(folder, engine)   # never the real database or pipeline outputs
    from scripts.init_db import init   # uses the app's engine: imported only now that it points here

    init()   # tables, and the admin user from ADMIN_USERNAME / ADMIN_PASSWORD
    db = SessionLocal()
    try:
        plant_standalone(db)
        if not plant_only:
            print("\nRunning detection on the standalone demo (ML/GNN training skipped: "
                  "it needs the main labelled dataset):")
            run_pipeline(db, with_ml=False)
            report(db, ml=False)
    finally:
        db.close()

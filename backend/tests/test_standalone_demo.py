"""The standalone demo: only the 22 scripted accounts and transactions, in a
database of its own, with the real rule engine, graph analysis, alerts and ring
detection run on it.

Each build runs in a subprocess (the demo points the app at its database before
the app's engine exists, which this test process has already created) and in a
temporary folder, against a stand-in "main" database whose files must come out
unchanged. Nothing here touches backend/data or your real database.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.demo.scenario import ROLES, STAGE_INFO, STAGES, scenario_transactions, stage_of
from app.ml.rules import RULE_CODES

BACKEND = Path(__file__).resolve().parents[1]
CODE_FOR = {code: name for name, code in RULE_CODES.items()}   # "R4" -> "fan_in"


def run_python(code: str, main_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """Run code with the app configured for a stand-in main installation in main_dir."""
    env = {**os.environ,
           "DATABASE_URL": "sqlite:///" + (main_dir / "main.db").as_posix(),
           "PIPELINE_OUTPUT_DIR": str(main_dir / "outputs"),
           "APP_ENV": "development", "DEMO_MODE": "",
           "SECRET_KEY": "test-only-secret-key-0123456789-abcdefghijklmnop",
           "ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "admin-test-password",
           "SMTP_HOST": "", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code), *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)


DEMO_CLI = """
    import sys
    import scripts.demo_scenario as d
    folder, copy_folder = sys.argv[1], sys.argv[2]
    d.STANDALONE = d.DemoEnvironment(folder, folder + ".lock", "standalone demo", " --standalone", standalone=True)
    d.COPY = d.DemoEnvironment(copy_folder, copy_folder + ".lock", "demo copy")
    d.main(sys.argv[3:])
"""


def fingerprint(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def main_install(tmp_path_factory):
    """A stand-in main installation: a database with its own accounts and an outputs folder."""
    main_dir = tmp_path_factory.mktemp("main")
    (main_dir / "outputs" / "saved_models").mkdir(parents=True)
    (main_dir / "outputs" / "saved_models" / "rings.json").write_text('{"rings": []}')
    con = sqlite3.connect(main_dir / "main.db")
    con.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, account_uid VARCHAR)")
    con.executemany("INSERT INTO accounts (account_uid) VALUES (?)", [(f"ACC{i:05d}",) for i in range(1, 51)])
    con.commit()
    con.close()
    return main_dir


@pytest.fixture(scope="module")
def built(main_install, tmp_path_factory):
    folder = tmp_path_factory.mktemp("standalone") / "demo_standalone"
    before = fingerprint(main_install)
    result = run_python(DEMO_CLI, main_install, str(folder), str(folder.parent / "copy"), "--standalone")
    assert result.returncode == 0, result.stdout + result.stderr
    assert fingerprint(main_install) == before          # the main installation was never touched
    return folder, result.stdout


def query(folder: Path, sql: str, *params):
    con = sqlite3.connect(f"file:{(folder / 'fraud_detection.db').as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


# 1-3: only the scenario
def test_only_the_scripted_accounts_and_transactions(built):
    folder, _ = built
    accounts = {uid for (uid,) in query(folder, "SELECT account_uid FROM accounts")}
    txns = {uid for (uid,) in query(folder, "SELECT txn_uid FROM transactions")}
    assert len(accounts) == 22 and accounts == set(ROLES)
    assert len(txns) == 22 and txns == {row["txn_uid"] for _, row in scenario_transactions()}
    assert not any(uid.startswith("ACC") for uid in accounts)   # nothing from the original dataset
    roles = [ROLES[uid] for uid in accounts]
    assert (roles.count("feeder"), roles.count("mule"), roles.count("collector"),
            roles.count("shell"), roles.count("cash-out")) == (9, 1, 1, 2, 9)
    assert query(folder, "SELECT username, role FROM users") == [("admin", "admin")]


# 4-5: every rule on its stage, every stage detected
def test_each_stage_triggers_its_rules(built):
    folder, _ = built
    stage = stage_of()
    fired = {s: set() for s in STAGES}
    for txn_uid, rule in query(folder, "SELECT txn_uid, rule FROM rule_hits"):
        fired[stage[txn_uid]].add(RULE_CODES[rule])
    for s in STAGES:
        assert set(STAGE_INFO[s]["expected_rules"]) <= fired[s], (s, fired[s])
    assert set().union(*fired.values()) == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert query(folder, "SELECT count(*) FROM transactions WHERE status = 'suspicious'") == [(22,)]


# 6: graph analysis and fraud-ring detection
def test_graph_and_ring_detection(built):
    folder, _ = built
    assert query(folder, "SELECT count(*) FROM graph_metrics") == [(22,)]
    assert query(folder, "SELECT count(*) FROM graph_metrics WHERE in_cycle = 1") == [(3,)]   # collector, shells
    rings = json.loads((folder / "saved_models" / "rings.json").read_text())
    assert rings["rings_found"] == 1
    ring = rings["rings"][0]
    assert set(ring["member_ids"]) == set(ROLES) and ring["main_account"] == "DEMO-COLLECTOR"
    assert ring["rules"] == ["R1", "R2", "R3", "R4", "R5", "R6"] and ring["risk"] == "High"
    assert (folder / "processed" / "features.csv").read_text().count("\n") == 23   # header + 22 accounts


# 6 (ML): no model is trained on 22 scripted accounts
def test_no_models_trained(built):
    folder, output = built
    assert sorted(p.name for p in (folder / "saved_models").iterdir()) == ["rings.json"]
    assert "ML Scoring" not in output and "ML/GNN training skipped" in output


# 7: alerts
def test_alerts_raised_for_the_flagged_transactions(built):
    folder, _ = built
    assert query(folder, "SELECT count(*) FROM alerts WHERE transaction_uid IS NOT NULL") == [(22,)]
    assert query(folder, "SELECT count(*) FROM alerts WHERE transaction_uid IS NULL") == [(0,)]   # no ML alerts


APP_FLOW = """
    import json, sys, uuid
    from scripts.demo_common import point_app_at
    point_app_at(sys.argv[1], demo_mode="standalone")
    from fastapi.testclient import TestClient
    from app.main import app

    out = {}
    with TestClient(app) as client:
        token = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-password"}).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        out["info"] = client.get("/api/system/info").json()
        scenario = client.get("/api/demo/scenario", headers=h).json()
        out["coverage"] = scenario["coverage"]
        out["stages"] = [(s["name"], s["detected"], s["flagged"], s["total"], s["rules_fired"]) for s in scenario["stages"]]
        out["ml_train"] = client.post("/api/ml/train", headers=h).status_code
        out["gnn_train"] = client.post("/api/gnn/train", json={"source": "synthetic", "model": "gcn", "epochs": 10}, headers=h).status_code
        out["accounts"] = client.get("/api/accounts", headers=h).json()["total"]
        out["transactions"] = client.get("/api/transactions", headers=h).json()["total"]
        detail = client.get("/api/accounts/DEMO-COLLECTOR/investigation", headers=h).json()
        out["collector_alerts"] = len(detail["alerts"])
        out["collector_txns"] = detail["transaction_count"]
        res = client.post("/api/accounts/DEMO-COLLECTOR/review",
                          json={"action": "confirm_fraud", "note": "Scenario collector", "transaction_uid": "DEMO-TXN014"}, headers=h).json()
        out["confirmed"] = res["account"]["fraud_status"]
        with client.websocket_connect("/api/notifications/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            out["ws_ready"] = ws.receive_json()["type"]
            txn = client.post("/api/transactions", json={"sender_uid": "DEMO-COLLECTOR", "receiver_uid": "DEMO-CASH01",
                                                         "amount": 25000}, headers={**h, "Idempotency-Key": str(uuid.uuid4())}).json()
            pushed = ws.receive_json()
        out["pushed"] = [pushed["type"], pushed["notification"]["account_uid"], pushed["notification"]["transaction_uid"] == txn["txn_uid"]]
        exports = [e["name"] for e in client.get("/api/reports/exports", headers=h).json()]
        out["exports_first"] = exports[0]
        csv = client.get("/api/reports/export/demo_scenario", headers=h).text
        out["scenario_csv_rows"] = csv.strip().count("\\n")
        pdf = client.get("/api/reports/summary-pdf", headers=h)
        out["pdf"] = [pdf.status_code, pdf.headers["content-type"], pdf.content[:4].decode()]
    print("RESULT " + json.dumps(out))
"""


# 7-8 and the API: investigation, confirmation, real-time alert, reports - against the standalone database
def test_app_on_the_standalone_demo(built, main_install, tmp_path):
    folder, _ = built
    work = tmp_path / "demo_standalone"
    shutil.copytree(folder, work)   # this test changes the data; leave the shared build as it was
    result = run_python(APP_FLOW, main_install, str(work))
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    out = json.loads(result.stdout.split("RESULT ", 1)[1])
    assert out["info"]["demo_mode"] == "standalone" and out["info"]["ml_training_available"] is False
    assert out["coverage"]["transactions_flagged"] == 22 and out["coverage"]["stages_detected"] == 4
    assert out["coverage"]["all_rules_fired"] is True and out["coverage"]["accounts_in_rings"] == 22
    assert [s[1] for s in out["stages"]] == [True, True, True, True]
    assert out["ml_train"] == 409 and out["gnn_train"] == 409            # explained, not attempted
    assert (out["accounts"], out["transactions"]) == (22, 22)
    assert out["collector_alerts"] > 0 and out["collector_txns"] == 12   # 1 in, 2 in the loop, 9 out
    assert out["confirmed"] == "Confirmed Fraud"
    assert out["ws_ready"] == "ready"
    assert out["pushed"] == ["notification", "DEMO-COLLECTOR", True]   # pushed when recorded
    assert out["exports_first"] == "demo_scenario" and out["scenario_csv_rows"] == 22
    assert out["pdf"] == [200, "application/pdf", "%PDF"]


def test_plant_only_leaves_detection_to_the_ui(main_install, tmp_path):
    folder = tmp_path / "demo_standalone"
    result = run_python(DEMO_CLI, main_install, str(folder), str(tmp_path / "copy"), "--standalone", "--plant-only")
    assert result.returncode == 0, result.stdout + result.stderr
    assert query(folder, "SELECT count(*) FROM accounts") == [(22,)]
    assert query(folder, "SELECT count(*) FROM transactions") == [(22,)]
    assert query(folder, "SELECT count(*) FROM rule_hits") == [(0,)]
    assert query(folder, "SELECT DISTINCT status FROM transactions") == [("normal",)]
    assert not (folder / "saved_models" / "rings.json").exists()
    assert (folder / "ready.txt").exists() and "--serve --standalone" in result.stdout


# 9: cleanup removes only the standalone demo
def test_cleanup_touches_nothing_else(main_install, tmp_path):
    folder = tmp_path / "demo_standalone"
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / "keep.txt").write_text("the full demo copy")
    assert run_python(DEMO_CLI, main_install, str(folder), str(copy), "--standalone", "--plant-only").returncode == 0
    before = fingerprint(main_install)
    result = run_python(DEMO_CLI, main_install, str(folder), str(copy), "--cleanup", "--standalone")
    assert result.returncode == 0 and "Deleted the standalone demo" in result.stdout
    assert not folder.exists()
    assert fingerprint(main_install) == before and (copy / "keep.txt").exists()
    again = run_python(DEMO_CLI, main_install, str(folder), str(copy), "--cleanup", "--standalone")
    assert "There's no standalone demo to delete." in again.stdout


def test_refuses_when_the_main_database_is_inside_the_demo_folder(main_install, tmp_path):
    folder = tmp_path / "demo_standalone"
    folder.mkdir()
    shutil.copy(main_install / "main.db", folder / "main.db")
    point_inside = [   # as if DATABASE_URL named a database inside the standalone folder
        "from app.config import settings",
        "settings.DATABASE_URL = 'sqlite:///' + folder.replace(chr(92), '/') + '/main.db'",
        "d.main(sys.argv[3:])",
    ]
    code = textwrap.dedent(DEMO_CLI).replace("d.main(sys.argv[3:])", "\n".join(point_inside))
    for args in (["--standalone"], ["--cleanup", "--standalone"]):
        result = run_python(code, main_install, str(folder), str(tmp_path / "copy"), *args)
        assert result.returncode != 0 and "DATABASE_URL points into" in result.stderr, args
        assert (folder / "main.db").exists()


def test_serving_needs_a_finished_build(tmp_path):
    import scripts.demo_scenario as d
    env = d.DemoEnvironment(str(tmp_path / "none"), str(tmp_path / "none.lock"), "standalone demo",
                            " --standalone", standalone=True)
    with pytest.raises(SystemExit, match="There's no standalone demo yet"):
        d.serve(env)


# 10: the existing commands work as before
def test_existing_commands_unchanged(monkeypatch):
    import scripts.demo_scenario as d
    calls = []
    monkeypatch.setattr(d, "build", lambda plant_only, env: calls.append(("build", plant_only, env.standalone)))
    monkeypatch.setattr(d, "build_standalone", lambda plant_only, env: calls.append(("standalone", plant_only, env.standalone)))
    monkeypatch.setattr(d, "serve", lambda env: calls.append(("serve", env.standalone)))
    monkeypatch.setattr(d, "cleanup", lambda env: calls.append(("cleanup", env.standalone)))
    for argv in ([], ["--plant-only"], ["--serve"], ["--cleanup"],
                 ["--standalone"], ["--plant-only", "--standalone"], ["--serve", "--standalone"],
                 ["--cleanup", "--standalone"]):
        d.main(argv)
    assert calls == [("build", False, False), ("build", True, False), ("serve", False), ("cleanup", False),
                     ("standalone", False, True), ("standalone", True, True), ("serve", True), ("cleanup", True)]
    with pytest.raises(SystemExit):
        d.build_parser().parse_args(["--plant-only", "--serve"])   # still mutually exclusive


COVERAGE_WITH_EXTRA = """
    import json, sys
    from datetime import datetime
    from scripts.demo_common import point_app_at
    point_app_at(sys.argv[1], demo_mode="standalone")
    from app.database import SessionLocal
    from app.demo import coverage
    from app.models.transaction import Transaction

    def txn(uid, sender, receiver, amount, when):
        return Transaction(txn_uid=uid, sender_uid=sender, receiver_uid=receiver, amount=amount, timestamp=when,
                           txn_type="transfer", status="normal", is_fraud=0, fraud_score=0.0)

    db = SessionLocal()
    db.add_all([txn("DEMO-BG0001", "DEMO-FEED01", "DEMO-MULE", 1200.0, datetime(2024, 3, 1)),   # background activity
                txn("TXN-LATER", "DEMO-COLLECTOR", "DEMO-CASH02", 5000.0, datetime(2024, 11, 20))])   # recorded later
    db.commit()
    data = coverage.report(db)
    links = {(l["source"], l["target"]): l["amount"] for l in data["graph"]["links"]}
    print("RESULT " + json.dumps({
        "count": data["other_transactions"]["count"],
        "recent": [t["txn_uid"] for t in data["other_transactions"]["recent"]],
        "feeder_link": links[("DEMO-FEED01", "DEMO-MULE")],
        "cashout_link": links[("DEMO-COLLECTOR", "DEMO-CASH02")],
    }))
"""


def test_coverage_leaves_out_background_activity(built, main_install, tmp_path):
    """The demo copy plants ordinary DEMO-BG activity around the scenario: it isn't
    "recorded after the scenario", and isn't part of the scenario's network."""
    folder, _ = built
    work = tmp_path / "demo_standalone"
    shutil.copytree(folder, work)
    result = run_python(COVERAGE_WITH_EXTRA, main_install, str(work))
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    out = json.loads(result.stdout.split("RESULT ", 1)[1])
    assert (out["count"], out["recent"]) == (1, ["TXN-LATER"])
    assert out["feeder_link"] == 52000.0                 # the scripted transfer only
    assert out["cashout_link"] == 98200.0 + 5000.0       # scripted, plus the later one


CLI_REPORT = """
    import sys
    from scripts.demo_common import point_app_at
    point_app_at(sys.argv[1], demo_mode="standalone")
    from app.database import SessionLocal
    from app.models.rule_hit import RuleHit
    from scripts import demo_plant

    db = SessionLocal()
    db.query(RuleHit).filter(RuleHit.rule == "circular").delete()   # as if R6 had missed the loop
    db.commit()
    demo_plant.report(db, ml=sys.argv[2] == "ml")
"""


def test_cli_report_comes_from_the_coverage_report(built, main_install, tmp_path):
    folder, output = built
    assert "Coverage: 22/22 transactions flagged, 4/4 stages detected, rules fired: R1 R2 R3 R4 R5 R6, " \
           "22/22 accounts in a fraud ring." in output
    assert "ML score" not in output
    assert re.search(r"DEMO-COLLECTOR +collector +High +[0-9]+ +RING001", output)   # role, risk, alerts, ring
    assert "RING001: 22 accounts, main DEMO-COLLECTOR" in output

    work = tmp_path / "demo_standalone"
    shutil.copytree(folder, work)
    for mode in ("ml", "no-ml"):
        result = run_python(CLI_REPORT, main_install, str(work), mode)
        assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
        assert "(designed to trigger R6: did not fire)" in result.stdout
        assert "3/4 stages detected" in result.stdout and "rules fired: R1 R2 R3 R4 R5," in result.stdout
        assert ("ML score" in result.stdout) == (mode == "ml")


FULL_MAIN = """
    from datetime import datetime
    from scripts.init_db import init
    init()
    from app.database import SessionLocal
    from app.models.account import Account
    db = SessionLocal()
    db.bulk_insert_mappings(Account, [dict(account_uid=f"ACC{i:05d}", customer_name=f"Customer {i}",
                                           created_at=datetime(2023, 1, 1)) for i in range(1, 51)])
    db.commit()
"""


def test_full_demo_copy_goes_where_its_environment_says(tmp_path):
    """The full demo's folder comes from its DemoEnvironment alone: copying, planting
    and marking it ready all happen there, never in the default backend/data/demo."""
    main_dir = tmp_path / "main"
    (main_dir / "outputs").mkdir(parents=True)
    assert run_python(FULL_MAIN, main_dir).returncode == 0
    default_copy = BACKEND / "data" / "demo"
    default_before = fingerprint(default_copy) if default_copy.exists() else None
    main_before = fingerprint(main_dir)

    copy = tmp_path / "copy"
    result = run_python(DEMO_CLI, main_dir, str(tmp_path / "standalone"), str(copy), "--plant-only")
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert query(copy, "SELECT count(*) FROM accounts WHERE account_uid LIKE 'DEMO-%'") == [(22,)]
    assert query(copy, "SELECT count(*) FROM accounts WHERE account_uid LIKE 'ACC%'") == [(50,)]
    assert (copy / "ready.txt").exists()
    assert (fingerprint(default_copy) if default_copy.exists() else None) == default_before
    assert fingerprint(main_dir) == main_before

    result = run_python(DEMO_CLI, main_dir, str(tmp_path / "standalone"), str(copy), "--cleanup")
    assert result.returncode == 0 and f"Deleted the demo copy ({copy})" in result.stdout
    assert not copy.exists()

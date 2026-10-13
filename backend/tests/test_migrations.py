"""Migrations add the new tables and columns to an existing database without losing rows."""
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.migrations import MIGRATIONS, run_migrations

OLD_SCHEMA = [
    """CREATE TABLE accounts (id INTEGER PRIMARY KEY, account_uid VARCHAR NOT NULL UNIQUE,
       customer_name VARCHAR NOT NULL, email VARCHAR, phone VARCHAR, account_type VARCHAR,
       created_at DATETIME, risk_level VARCHAR, fraud_score FLOAT, is_fraud INTEGER, is_active INTEGER)""",
    """CREATE TABLE transactions (id INTEGER PRIMARY KEY, txn_uid VARCHAR NOT NULL UNIQUE,
       sender_uid VARCHAR NOT NULL, receiver_uid VARCHAR NOT NULL, amount FLOAT NOT NULL,
       timestamp DATETIME, txn_type VARCHAR, status VARCHAR, is_fraud INTEGER, fraud_score FLOAT)""",
    "INSERT INTO accounts (account_uid, customer_name, risk_level, fraud_score) VALUES ('ACC00001', 'A', 'High', 0.9)",
    "INSERT INTO transactions (txn_uid, sender_uid, receiver_uid, amount) VALUES ('TXN0000001', 'ACC00001', 'ACC00001', 10)",
]


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_existing_database_keeps_its_rows(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path.as_posix()}/old.db")
    with engine.begin() as conn:
        for statement in OLD_SCHEMA:
            conn.execute(text(statement))

    applied = run_migrations(engine)

    assert applied == [version for version, _ in MIGRATIONS]
    assert {"review_status", "review_updated_at", "fraud_confirmed_by", "fraud_confirmed_at"} <= _columns(engine, "accounts")
    assert "idempotency_key" in _columns(engine, "transactions")
    assert {"account_status_events", "fraud_notifications", "notification_reads", "email_deliveries"} \
        <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert conn.execute(text("SELECT account_uid, fraud_score, review_status FROM accounts")).all() \
            == [("ACC00001", 0.9, None)]
        assert conn.execute(text("SELECT count(*) FROM transactions")).scalar() == 1
    assert run_migrations(engine) == []   # a second run changes nothing


def test_fresh_database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path.as_posix()}/new.db")
    run_migrations(engine)   # create_all already made every column; the migrations must cope
    assert "review_status" in _columns(engine, "accounts")
    assert run_migrations(engine) == []

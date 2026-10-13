"""Schema migrations: bring an existing database up to date without losing data.

create_all() adds tables that don't exist yet, but never changes a table that
does, so new columns on existing tables are added here. Each migration runs
once (recorded in schema_migrations) and is written to be safe on a database
that already has its changes - a fresh one, where create_all just made the
tables with every column. Nothing here drops or rewrites data.
"""
from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import Base


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if column in {c["name"] for c in inspect(conn).get_columns(table)}:
        return
    try:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
    except OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            raise
        # another process starting at the same moment added it first


def _account_review_status(conn) -> None:
    _add_column(conn, "accounts", "review_status", "VARCHAR")
    _add_column(conn, "accounts", "review_updated_at", "DATETIME")
    _add_column(conn, "accounts", "fraud_confirmed_by", "VARCHAR")
    _add_column(conn, "accounts", "fraud_confirmed_at", "DATETIME")
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_accounts_review_status ON accounts (review_status)"))


def _transaction_idempotency_key(conn) -> None:
    _add_column(conn, "transactions", "idempotency_key", "VARCHAR")
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_transactions_idempotency_key "
                      "ON transactions (idempotency_key)"))


# (version, migration) - append only; never edit or reorder one that has shipped
MIGRATIONS = [
    ("2026_10_13_account_review_status", _account_review_status),
    ("2026_10_13_transaction_idempotency_key", _transaction_idempotency_key),
]


def run_migrations(engine) -> list[str]:
    """Create missing tables, then apply pending migrations. Returns the versions applied."""
    from app import models  # noqa: F401  (registers every table on Base.metadata)

    Base.metadata.create_all(bind=engine)
    applied = []
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations "
                          "(version VARCHAR PRIMARY KEY, applied_at VARCHAR NOT NULL)"))
        done = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}
        for version, migrate in MIGRATIONS:
            if version in done:
                continue
            migrate(conn)
            conn.execute(text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :t)"),
                         {"v": version, "t": datetime.utcnow().isoformat(timespec="seconds")})
            applied.append(version)
    return applied


def run_migrations_safely(engine) -> list[str]:
    """run_migrations, tolerating another process that applied the same ones
    at the same moment (two app processes starting together): a second pass
    then finds the work done."""
    try:
        return run_migrations(engine)
    except (IntegrityError, OperationalError):
        return run_migrations(engine)

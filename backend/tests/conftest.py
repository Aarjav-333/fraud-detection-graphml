"""Test setup: every test runs against a throwaway database and output folder.

The app builds its database engine from DATABASE_URL when first imported, so
the environment is set here, before any test imports it - and checked, so the
suite refuses to run against a real database.
"""
import os
import socket
import tempfile
import threading
import queue
import uuid
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="fraudgraph-tests-")
os.environ.update({
    "DATABASE_URL": "sqlite:///" + Path(_TMP, "test.db").as_posix(),
    "PIPELINE_OUTPUT_DIR": _TMP,
    "APP_ENV": "development",
    "SECRET_KEY": "test-only-secret-key-0123456789-abcdefghijklmnop",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "admin-test-password",
    "SMTP_HOST": "",
    "EMAIL_FROM": "",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402

assert settings.DATABASE_URL.endswith(Path(_TMP, "test.db").as_posix()), "tests must use their own database"

from app.core.security import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402  (runs the migrations on the test database)
from app.models.account import Account  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import mailer  # noqa: E402

PASSWORD = "test-password-123"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _login(client, username):
    res = client.post("/api/auth/login", data={"username": username, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture(scope="session")
def users(client):
    """Bearer headers for an admin, two analysts and a viewer."""
    session = SessionLocal()
    for name, role in [("t_admin", "admin"), ("t_analyst", "analyst"),
                       ("t_analyst2", "analyst"), ("t_viewer", "viewer")]:
        session.add(User(username=name, hashed_password=hash_password(PASSWORD), role=role))
    session.commit()
    session.close()
    return {role: _login(client, name) for role, name in
            [("admin", "t_admin"), ("analyst", "t_analyst"), ("analyst2", "t_analyst2"), ("viewer", "t_viewer")]}


@pytest.fixture
def login(client):
    """Log in again (a new token, as after a page refresh or a new session)."""
    return lambda username: _login(client, username)


@pytest.fixture
def make_account(db):
    """Create an account with a unique id; returns its uid."""
    def make(email="holder@fraudgraph-test-inbox.com", fraud_score=0.0, risk_level="Low", name="Asha Verma"):
        uid = "T" + uuid.uuid4().hex[:7].upper()
        db.add(Account(account_uid=uid, customer_name=name, email=email, account_type="Savings",
                       fraud_score=fraud_score, risk_level=risk_level))
        db.commit()
        return uid
    return make


@pytest.fixture
def make_txn(db):
    """Record a transaction directly in the database (history, not a new event)."""
    def make(sender, receiver, amount=1000.0, status="normal"):
        uid = "TT" + uuid.uuid4().hex[:10].upper()
        db.add(Transaction(txn_uid=uid, sender_uid=sender, receiver_uid=receiver, amount=amount,
                           txn_type="transfer", status=status))
        db.commit()
        return uid
    return make


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Inbox:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        from email import message_from_bytes, policy
        self.messages.append({"to": envelope.rcpt_tos,
                              "message": message_from_bytes(envelope.content, policy=policy.default)})
        return "250 Message accepted"


@pytest.fixture
def smtp(monkeypatch):
    """A real SMTP server on localhost that keeps what it receives, with the
    app configured to send through it (no retry delays)."""
    from aiosmtpd.controller import Controller

    inbox = _Inbox()
    port = free_port()
    controller = Controller(inbox, hostname="127.0.0.1", port=port)
    controller.start()
    _use_smtp(monkeypatch, port)
    inbox.port = port
    yield inbox
    controller.stop()


def _use_smtp(monkeypatch, port):
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", port)
    monkeypatch.setattr(settings, "SMTP_SECURITY", "none")
    monkeypatch.setattr(settings, "SMTP_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(settings, "EMAIL_FROM", "fraud-alerts@fraudgraph-test-bank.com")
    monkeypatch.setattr(mailer, "RETRY_DELAYS", (0, 0))


@pytest.fixture
def smtp_down(monkeypatch):
    """The app configured for an SMTP server that isn't running."""
    port = free_port()
    _use_smtp(monkeypatch, port)
    return port


def receive(ws, timeout=5.0):
    """ws.receive_json(), but fail instead of hanging if nothing arrives."""
    box = queue.Queue()
    threading.Thread(target=lambda: box.put(_safe(ws.receive_json)), daemon=True).start()
    try:
        result = box.get(timeout=timeout)
    except queue.Empty:
        raise AssertionError(f"nothing received within {timeout}s") from None
    if isinstance(result, BaseException):
        raise result
    return result


def _safe(fn):
    try:
        return fn()
    except BaseException as exc:   # handed to the test thread
        return exc

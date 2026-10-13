"""Real-time fraud notifications for analysts.

When a transaction is recorded, its sender is checked: if an analyst has
confirmed that account as fraudulent, a High-priority alert (on the Fraud
Alerts page) and a notification are stored, then every open notification
stream is woken to push it. The database is the source of truth - streams
re-read it, so a notification survives refreshes, logins and restarts, and a
stream that missed a wake-up (or runs in another process) still picks it up
on its periodic check. Only a manual confirmation counts: a high ML score or
rule hit never triggers this.
"""
import asyncio
import logging
import threading
from datetime import datetime

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.formatting import format_inr
from app.ml.alerts import next_alert_num
from app.models.account import Account, REVIEW_CONFIRMED_FRAUD
from app.models.alert import Alert
from app.models.transaction import Transaction
from app.models.notification import (
    FraudNotification, NotificationRead, KIND_CONFIRMED_FRAUD_ACTIVITY,
)

log = logging.getLogger(__name__)


class _Broker:
    """Wakes the open notification streams. Publishing is safe from any thread
    (request handlers run in a thread pool; streams live on the event loop)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._waiters: dict[asyncio.Event, asyncio.AbstractEventLoop] = {}

    def subscribe(self) -> asyncio.Event:
        event = asyncio.Event()
        with self._lock:
            self._waiters[event] = asyncio.get_running_loop()
        return event

    def unsubscribe(self, event: asyncio.Event) -> None:
        with self._lock:
            self._waiters.pop(event, None)

    def publish(self) -> None:
        with self._lock:
            waiters = list(self._waiters.items())
        for event, loop in waiters:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:   # that stream's event loop has shut down
                self.unsubscribe(event)


broker = _Broker()


def _message(account_uid: str, amount: float) -> str:
    return (f"High Priority Fraud Alert: Account {account_uid}, previously confirmed as fraudulent, "
            f"has initiated a new transaction of {format_inr(amount)}. "
            "Immediate investigation is recommended.")


CHUNK = 500                 # values per IN (...) list, well under SQLite's variable limit
ALERT_NUMBER_ATTEMPTS = 5   # tries if a concurrent request takes the same alert number


def _already_notified(db: Session, txn_uid: str) -> bool:
    return db.query(FraudNotification.id).filter_by(
        kind=KIND_CONFIRMED_FRAUD_ACTIVITY, transaction_uid=txn_uid).first() is not None


def _notify(db: Session, account_uid: str, txn_uid: str) -> FraudNotification | None:
    """Store the alert and notification for one transaction, committed on their
    own. None if it was already notified. Alert numbers are read-then-incremented,
    so a concurrent request can take the same one: then this tries again with a
    fresh number instead of mistaking the conflict for a duplicate."""
    for _ in range(ALERT_NUMBER_ATTEMPTS):
        if _already_notified(db, txn_uid):
            return None
        account = db.query(Account).filter_by(account_uid=account_uid).one()
        txn = db.query(Transaction).filter_by(txn_uid=txn_uid).one()
        notification = _build(db, account, txn)
        try:
            db.commit()
            return notification
        except IntegrityError:
            db.rollback()   # the alert number was taken meanwhile, or another request notified first
    log.error("Could not record the fraud notification for %s: alert numbers kept colliding", txn_uid)
    return None


def _build(db: Session, account: Account, txn) -> FraudNotification:
    score = account.fraud_score
    alert = Alert(
        alert_uid=f"ALT{next_alert_num(db):06d}",
        transaction_uid=txn.txn_uid,
        account_uid=account.account_uid,
        reason="Transaction by an account confirmed as fraud by an analyst",
        fraud_score=round(float(score or 0.0), 4),
        risk_level="High",
        status="Pending",
        created_at=datetime.utcnow(),
    )
    notification = FraudNotification(
        kind=KIND_CONFIRMED_FRAUD_ACTIVITY,
        priority="High",
        alert_uid=alert.alert_uid,
        account_uid=account.account_uid,
        transaction_uid=txn.txn_uid,
        amount=txn.amount,
        transaction_time=txn.timestamp,
        account_status=account.fraud_status,
        risk_score=score,
        message=_message(account.account_uid, txn.amount),
        created_at=datetime.utcnow(),
    )
    db.add_all([alert, notification])
    return notification


def confirmed_fraud_senders(db: Session, senders) -> set[str]:
    """Which of these accounts an analyst has confirmed as fraud."""
    senders = list(set(senders))
    found = set()
    for i in range(0, len(senders), CHUNK):
        found |= {uid for (uid,) in db.query(Account.account_uid).filter(
            Account.account_uid.in_(senders[i:i + CHUNK]), Account.review_status == REVIEW_CONFIRMED_FRAUD)}
    return found


def notify_confirmed_fraud_activity(db: Session, transactions) -> list[FraudNotification]:
    """Store a notification for each transaction sent by a confirmed-fraud
    account. Idempotent: a transaction already notified is skipped."""
    pairs = [(t.sender_uid, t.txn_uid) for t in transactions]
    flagged = confirmed_fraud_senders(db, [sender for sender, _ in pairs])
    created = [n for sender, txn_uid in pairs if sender in flagged
               for n in [_notify(db, sender, txn_uid)] if n is not None]
    if created:
        broker.publish()
    return created


def on_transactions_recorded(db: Session, transactions) -> int:
    """The hook for every place that records transactions. Never raises: the
    transactions are already saved, and a notification problem must not turn
    that into an error for whoever recorded them."""
    try:
        return len(notify_confirmed_fraud_activity(db, transactions))
    except Exception:
        db.rollback()
        log.exception("Could not create fraud notifications for transactions %s",
                      [t.txn_uid for t in transactions][:20])
        return 0


# ------------------------------------------------------------------ reading

def serialize(n: FraudNotification, read_at: datetime | None) -> dict:
    return {
        "id": n.id,
        "kind": n.kind,
        "priority": n.priority,
        "alert_uid": n.alert_uid,
        "account_uid": n.account_uid,
        "transaction_uid": n.transaction_uid,
        "amount": n.amount,
        "transaction_time": n.transaction_time.isoformat() if n.transaction_time else None,
        "account_status": n.account_status,
        "risk_score": n.risk_score,
        "message": n.message,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "read": read_at is not None,
        "read_at": read_at.isoformat() if read_at else None,
    }


def _with_read_state(db: Session, user_id: int):
    return (db.query(FraudNotification, NotificationRead.read_at)
              .outerjoin(NotificationRead, and_(NotificationRead.notification_id == FraudNotification.id,
                                                NotificationRead.user_id == user_id)))


def list_for_user(db: Session, user_id: int, skip: int = 0, limit: int = 25,
                  unread_only: bool = False, account_uid: str | None = None,
                  after_id: int | None = None) -> tuple[int, list[dict]]:
    query = _with_read_state(db, user_id)
    if unread_only:
        query = query.filter(NotificationRead.id.is_(None))
    if account_uid:
        query = query.filter(FraudNotification.account_uid == account_uid)
    if after_id is not None:
        query = query.filter(FraudNotification.id > after_id)
        rows = query.order_by(FraudNotification.id).limit(limit).all()
        return len(rows), [serialize(n, read_at) for n, read_at in rows]
    total = query.count()
    rows = query.order_by(FraudNotification.id.desc()).offset(skip).limit(limit).all()
    return total, [serialize(n, read_at) for n, read_at in rows]


def unread_count(db: Session, user_id: int) -> int:
    return (db.query(func.count(FraudNotification.id))
              .outerjoin(NotificationRead, and_(NotificationRead.notification_id == FraudNotification.id,
                                                NotificationRead.user_id == user_id))
              .filter(NotificationRead.id.is_(None)).scalar())


def latest_id(db: Session) -> int:
    return db.query(func.max(FraudNotification.id)).scalar() or 0


def set_read(db: Session, notification_id: int, user_id: int, read: bool) -> bool:
    """Mark one notification read or unread for this analyst. False if it doesn't exist."""
    if db.get(FraudNotification, notification_id) is None:
        return False
    receipt = db.query(NotificationRead).filter_by(notification_id=notification_id, user_id=user_id).first()
    if read and receipt is None:
        db.add(NotificationRead(notification_id=notification_id, user_id=user_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()   # marked read by another request at the same moment
    elif not read and receipt is not None:
        db.delete(receipt)
        db.commit()
    broker.publish()   # other open tabs update their unread count
    return True


def mark_all_read(db: Session, user_id: int) -> int:
    unread = [n_id for (n_id,) in db.query(FraudNotification.id)
              .outerjoin(NotificationRead, and_(NotificationRead.notification_id == FraudNotification.id,
                                                NotificationRead.user_id == user_id))
              .filter(NotificationRead.id.is_(None))]
    if unread:
        db.add_all([NotificationRead(notification_id=n_id, user_id=user_id) for n_id in unread])
        try:
            db.commit()
        except IntegrityError:   # some were marked read meanwhile; do the rest one by one
            db.rollback()
            for n_id in unread:
                set_read(db, n_id, user_id, True)
        broker.publish()
    return len(unread)

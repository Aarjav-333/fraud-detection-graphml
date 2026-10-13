from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey, UniqueConstraint
from app.database import Base

KIND_CONFIRMED_FRAUD_ACTIVITY = "confirmed_fraud_activity"


class FraudNotification(Base):
    """A notification for fraud analysts, raised by a backend event (for now: a
    transaction by an account an analyst confirmed as fraudulent). One per
    (kind, transaction), so a repeated event can't notify twice."""
    __tablename__ = "fraud_notifications"
    __table_args__ = (UniqueConstraint("kind", "transaction_uid", name="uq_notification_kind_txn"),)

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False)
    priority = Column(String, nullable=False, default="High")
    alert_uid = Column(String, index=True)          # the alert raised alongside, on the Fraud Alerts page
    account_uid = Column(String, index=True, nullable=False)
    transaction_uid = Column(String, index=True)
    amount = Column(Float)
    transaction_time = Column(DateTime)
    account_status = Column(String)                 # the account's fraud status when it happened
    risk_score = Column(Float)                      # the account's ML fraud score at the time, if any
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class NotificationRead(Base):
    """Read receipts, per analyst: a notification is unread for anyone without one."""
    __tablename__ = "notification_reads"
    __table_args__ = (UniqueConstraint("notification_id", "user_id", name="uq_notification_read"),)

    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("fraud_notifications.id"), index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    read_at = Column(DateTime, default=datetime.utcnow)

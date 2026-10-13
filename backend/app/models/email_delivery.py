from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base

# pending: queued or being sent · sent · failed: can be retried · skipped: no usable address
EMAIL_PENDING, EMAIL_SENT, EMAIL_FAILED, EMAIL_SKIPPED = "pending", "sent", "failed", "skipped"


class EmailDelivery(Base):
    """An email to an account holder and what happened to it. One per status
    change (status_event_id is unique), so confirming an account twice can't
    send the confirmation email twice."""
    __tablename__ = "email_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False)                 # e.g. fraud_confirmation
    account_uid = Column(String, index=True, nullable=False)
    status_event_id = Column(Integer, unique=True)        # the AccountStatusEvent that triggered it
    recipient_masked = Column(String)                     # the address, partly hidden, for the log
    subject = Column(String)
    status = Column(String, nullable=False, default=EMAIL_PENDING)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    requested_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_attempt_at = Column(DateTime)
    sent_at = Column(DateTime)

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base


class AccountStatusEvent(Base):
    """One change to an account's manual review status: the audit trail of who
    marked it under review, confirmed it as fraud, or cleared it, and why."""
    __tablename__ = "account_status_events"

    id = Column(Integer, primary_key=True, index=True)
    account_uid = Column(String, index=True, nullable=False)
    from_status = Column(String)            # None = not under review
    to_status = Column(String)              # None = cleared
    changed_by = Column(String, nullable=False)      # analyst username
    changed_by_id = Column(Integer)
    note = Column(Text)
    transaction_uid = Column(String)        # the transaction the decision refers to, if any
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

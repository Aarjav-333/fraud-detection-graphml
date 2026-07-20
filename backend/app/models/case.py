from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_uid = Column(String, unique=True, index=True)
    alert_uid = Column(String, index=True)
    account_uid = Column(String, index=True)
    notes = Column(Text)
    assigned_to = Column(String)
    # Open / Under Investigation / Confirmed Fraud / False Positive / Closed
    status = Column(String, default="Open")
    final_decision = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

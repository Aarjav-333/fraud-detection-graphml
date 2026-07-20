from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float
from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_uid = Column(String, unique=True, index=True)
    transaction_uid = Column(String, index=True)
    account_uid = Column(String, index=True)
    reason = Column(String)
    fraud_score = Column(Float, default=0.0)
    risk_level = Column(String, default="Low")
    # Pending / Under Review / Confirmed Fraud / False Positive / Resolved
    status = Column(String, default="Pending")
    created_at = Column(DateTime, default=datetime.utcnow)

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float
from app.database import Base

# Manual review outcomes, set only by a fraud analyst (never by the ML or rule steps)
REVIEW_UNDER_REVIEW = "Under Review"
REVIEW_CONFIRMED_FRAUD = "Confirmed Fraud"
REVIEW_STATUSES = (REVIEW_UNDER_REVIEW, REVIEW_CONFIRMED_FRAUD)

# What analysts see, combining the manual review with the automated signals
STATUS_NORMAL = "Normal"
STATUS_SUSPICIOUS = "Suspicious"
FRAUD_STATUSES = (STATUS_NORMAL, STATUS_SUSPICIOUS, REVIEW_UNDER_REVIEW, REVIEW_CONFIRMED_FRAUD)
SUSPICIOUS_SCORE = 0.8                     # ML score that marks an account Suspicious (alerts use it too)
SUSPICIOUS_RISK_LEVELS = ("Medium", "High")  # risk levels the rule engine raises


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_uid = Column(String, unique=True, index=True, nullable=False)  # e.g. ACC00001
    customer_name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    account_type = Column(String)                 # savings / current / wallet ...
    created_at = Column(DateTime, default=datetime.utcnow)
    risk_level = Column(String, default="Low")    # Low / Medium / High (system output)
    fraud_score = Column(Float, default=0.0)       # system output
    is_fraud = Column(Integer, default=0)          # ground-truth label (from synthetic data)
    is_active = Column(Integer, default=1)         # 1 = active, 0 = deactivated
    # Manual fraud review by an analyst: None, "Under Review" or "Confirmed Fraud".
    # Kept apart from fraud_score / risk_level / is_fraud, so a model or rule never
    # counts as a confirmation. History lives in account_status_events.
    review_status = Column(String, index=True)
    review_updated_at = Column(DateTime)
    fraud_confirmed_by = Column(String)
    fraud_confirmed_at = Column(DateTime)

    @property
    def fraud_status(self) -> str:
        """Normal / Suspicious (rules or ML flagged it) / Under Review / Confirmed Fraud."""
        if self.review_status in REVIEW_STATUSES:
            return self.review_status
        if (self.fraud_score or 0) >= SUSPICIOUS_SCORE or self.risk_level in SUSPICIOUS_RISK_LEVELS:
            return STATUS_SUSPICIOUS
        return STATUS_NORMAL

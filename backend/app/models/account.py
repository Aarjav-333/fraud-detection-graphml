from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float
from app.database import Base


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

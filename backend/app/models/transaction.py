from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    txn_uid = Column(String, unique=True, index=True, nullable=False)
    sender_uid = Column(String, index=True, nullable=False)     # references Account.account_uid
    receiver_uid = Column(String, index=True, nullable=False)   # references Account.account_uid
    amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    txn_type = Column(String)                    # transfer / payment / withdrawal ...
    status = Column(String, default="normal")    # normal / suspicious
    is_fraud = Column(Integer, default=0)        # ground-truth label if known (0/1)
    fraud_score = Column(Float, default=0.0)

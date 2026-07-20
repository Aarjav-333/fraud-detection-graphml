from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class TransactionBase(BaseModel):
    sender_uid: str
    receiver_uid: str
    amount: float
    txn_type: Optional[str] = "transfer"
    timestamp: Optional[datetime] = None


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    txn_type: Optional[str] = None
    status: Optional[str] = None


class TransactionOut(BaseModel):
    id: int
    txn_uid: str
    sender_uid: str
    receiver_uid: str
    amount: float
    timestamp: datetime
    txn_type: Optional[str] = None
    status: str
    is_fraud: int
    fraud_score: float
    model_config = {"from_attributes": True}


class TransactionList(BaseModel):
    total: int
    items: List[TransactionOut]


class UploadResult(BaseModel):
    inserted: int
    skipped: int
    errors: List[str]

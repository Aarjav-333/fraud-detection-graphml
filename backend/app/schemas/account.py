from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class AccountBase(BaseModel):
    customer_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    account_type: Optional[str] = None
    risk_level: Optional[str] = "Low"


class AccountCreate(AccountBase):
    account_uid: Optional[str] = None  # auto-generated when omitted


class AccountUpdate(BaseModel):
    customer_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    account_type: Optional[str] = None
    risk_level: Optional[str] = None


class AccountOut(AccountBase):
    id: int
    account_uid: str
    created_at: datetime
    fraud_score: float
    is_fraud: int
    is_active: int
    # Normal / Suspicious / Under Review / Confirmed Fraud (see Account.fraud_status)
    fraud_status: str
    review_status: Optional[str] = None
    review_updated_at: Optional[datetime] = None
    fraud_confirmed_by: Optional[str] = None
    fraud_confirmed_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class AccountList(BaseModel):
    total: int
    items: List[AccountOut]

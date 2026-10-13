from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, ConfigDict, field_validator

# A manual KYC assessment made at onboarding. Not the computed risk_level.
OnboardingRisk = Optional[Literal["Low", "Medium", "High"]]
RISK_LEVEL_IS_COMPUTED = ("risk_level is computed by the rule engine and can't be changed. "
                          "Use onboarding_risk_category for a manual (KYC) assessment.")


class _AccountInput(BaseModel):
    # Unknown fields are refused rather than silently dropped, so a typo or a
    # computed field (fraud_score, review_status...) gets a clear 422, not a
    # misleading success.
    model_config = ConfigDict(extra="forbid")

    email: Optional[str] = None
    phone: Optional[str] = None
    account_type: Optional[str] = None
    onboarding_risk_category: OnboardingRisk = None
    # Computed by the rule engine. Accepted only as the value the account already
    # has (clients that echo it back, like the previous frontend, keep working);
    # trying to change it is refused.
    risk_level: Optional[str] = None

    @field_validator("customer_name", check_fields=False)
    @classmethod
    def _name_not_empty(cls, value):
        if value is None or not value.strip():
            raise ValueError("customer_name can't be empty")
        return value


class AccountCreate(_AccountInput):
    customer_name: str
    account_uid: Optional[str] = None  # auto-generated when omitted

    @field_validator("risk_level")
    @classmethod
    def _starts_low(cls, value):
        if value not in (None, "Low"):
            raise ValueError("New accounts start at Low. " + RISK_LEVEL_IS_COMPUTED)
        return value


class AccountUpdate(_AccountInput):
    customer_name: Optional[str] = None   # if sent, it can't be null or empty


class AccountOut(BaseModel):
    id: int
    account_uid: str
    customer_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    account_type: Optional[str] = None
    created_at: datetime
    risk_level: Optional[str] = "Low"   # computed by the rule engine (Low until rules flag the account)
    # Any stored value is shown as it is: a bad row must not break the whole list
    onboarding_risk_category: Optional[str] = None
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

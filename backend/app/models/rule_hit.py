from sqlalchemy import Column, Integer, String
from app.database import Base


class RuleHit(Base):
    """Which rule flagged which transaction, from the latest rule engine run."""
    __tablename__ = "rule_hits"

    id = Column(Integer, primary_key=True, index=True)
    txn_uid = Column(String, index=True, nullable=False)
    rule = Column(String, nullable=False)          # key of rules.RULE_LABELS, e.g. "fan_in"

import re
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountUpdate


def _next_account_uid(db: Session) -> str:
    """Generate the next ACC##### id based on the current maximum."""
    max_num = 0
    for (uid,) in db.query(Account.account_uid).all():
        m = re.match(r"ACC(\d+)$", uid or "")
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"ACC{max_num + 1:05d}"


def list_accounts(db: Session, skip: int = 0, limit: int = 25,
                  q: Optional[str] = None, active_only: bool = False):
    query = db.query(Account)
    if active_only:
        query = query.filter(Account.is_active == 1)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Account.account_uid.ilike(like),
            Account.customer_name.ilike(like),
            Account.email.ilike(like),
        ))
    total = query.count()
    items = query.order_by(Account.id).offset(skip).limit(limit).all()
    return total, items


def get_account(db: Session, account_uid: str) -> Optional[Account]:
    return db.query(Account).filter(Account.account_uid == account_uid).first()


def create_account(db: Session, data: AccountCreate) -> Account:
    uid = data.account_uid or _next_account_uid(db)
    acc = Account(
        account_uid=uid,
        customer_name=data.customer_name,
        email=data.email,
        phone=data.phone,
        account_type=data.account_type,
        risk_level=data.risk_level or "Low",
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def update_account(db: Session, account_uid: str, data: AccountUpdate) -> Optional[Account]:
    acc = get_account(db, account_uid)
    if not acc:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(acc, field, value)
    db.commit()
    db.refresh(acc)
    return acc


def set_active(db: Session, account_uid: str, active: bool) -> Optional[Account]:
    acc = get_account(db, account_uid)
    if not acc:
        return None
    acc.is_active = 1 if active else 0
    db.commit()
    db.refresh(acc)
    return acc

import re
from datetime import datetime
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.transaction import Transaction
from app.models.account import Account
from app.schemas.transaction import TransactionCreate, TransactionUpdate


def next_txn_uid(db: Session) -> str:
    max_num = 0
    last = db.query(Transaction.txn_uid).order_by(Transaction.id.desc()).first()
    if last and last[0]:
        m = re.match(r"TXN(\d+)$", last[0])
        if m:
            max_num = int(m.group(1))
    return f"TXN{max_num + 1:07d}"


def account_exists(db: Session, account_uid: str) -> bool:
    return db.query(Account.id).filter(Account.account_uid == account_uid).first() is not None


def list_transactions(db: Session, skip: int = 0, limit: int = 25,
                      q: Optional[str] = None, fraud_only: bool = False,
                      status: Optional[str] = None):
    query = db.query(Transaction)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Transaction.txn_uid.ilike(like),
            Transaction.sender_uid.ilike(like),
            Transaction.receiver_uid.ilike(like),
        ))
    if fraud_only:
        query = query.filter(Transaction.is_fraud == 1)
    if status:
        query = query.filter(Transaction.status == status)
    total = query.count()
    items = query.order_by(Transaction.timestamp.desc()).offset(skip).limit(limit).all()
    return total, items


def get_transaction(db: Session, txn_uid: str) -> Optional[Transaction]:
    return db.query(Transaction).filter(Transaction.txn_uid == txn_uid).first()


def create_transaction(db: Session, data: TransactionCreate) -> Transaction:
    txn = Transaction(
        txn_uid=next_txn_uid(db),
        sender_uid=data.sender_uid,
        receiver_uid=data.receiver_uid,
        amount=data.amount,
        timestamp=data.timestamp or datetime.utcnow(),
        txn_type=data.txn_type or "transfer",
        status="normal",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def update_transaction(db: Session, txn_uid: str, data: TransactionUpdate) -> Optional[Transaction]:
    txn = get_transaction(db, txn_uid)
    if not txn:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(txn, field, value)
    db.commit()
    db.refresh(txn)
    return txn


def delete_transaction(db: Session, txn_uid: str) -> bool:
    txn = get_transaction(db, txn_uid)
    if not txn:
        return False
    db.delete(txn)
    db.commit()
    return True

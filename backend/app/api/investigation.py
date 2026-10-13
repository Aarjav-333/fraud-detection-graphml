"""Fraud investigation of one account: its evidence, review status and history.

Fraud analysts only. Confirming fraud is a separate, explicit step from any
ML prediction; it records the analyst and time, and emails the account holder
from the backend once the change is saved.
"""
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_fraud_analyst
from app.models.account import Account
from app.models.account_status_event import AccountStatusEvent
from app.models.alert import Alert
from app.models.case import Case
from app.models.email_delivery import EmailDelivery, EMAIL_PENDING, EMAIL_SENT
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.account import AccountOut
from app.schemas.transaction import TransactionOut
from app.services import fraud_review, mailer, notifications

router = APIRouter(prefix="/api/accounts", tags=["investigation"],
                   dependencies=[Depends(require_fraud_analyst)])

RECENT = 100


class ReviewRequest(BaseModel):
    action: Literal["under_review", "confirm_fraud", "clear"]
    note: str = Field("", max_length=2000)
    transaction_uid: Optional[str] = Field(None, max_length=50)


def _account_or_404(db: Session, account_uid: str) -> Account:
    account = db.query(Account).filter_by(account_uid=account_uid).first()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/{account_uid}/investigation")
def investigation(account_uid: str, db: Session = Depends(get_db),
                  user: User = Depends(require_fraud_analyst)):
    account = _account_or_404(db, account_uid)
    involved = or_(Transaction.sender_uid == account_uid, Transaction.receiver_uid == account_uid)
    txns = db.query(Transaction).filter(involved).order_by(Transaction.timestamp.desc()).limit(RECENT).all()
    txn_count = db.query(Transaction.id).filter(involved).count()
    own_txns = db.query(Transaction.txn_uid).filter(involved)
    alerts = (db.query(Alert)
                .filter(or_(Alert.account_uid == account_uid, Alert.transaction_uid.in_(own_txns)))
                .order_by(Alert.id.desc()).limit(RECENT).all())
    cases = db.query(Case).filter_by(account_uid=account_uid).order_by(Case.id.desc()).all()
    events = (db.query(AccountStatusEvent).filter_by(account_uid=account_uid)
                .order_by(AccountStatusEvent.id.desc()).all())
    emails = (db.query(EmailDelivery).filter_by(account_uid=account_uid)
                .order_by(EmailDelivery.id.desc()).all())
    _, account_notifications = notifications.list_for_user(db, user.id, limit=20, account_uid=account_uid)
    return {
        "account": AccountOut.model_validate(account),
        "transactions": [TransactionOut.model_validate(t) for t in txns],
        "transaction_count": txn_count,
        "alerts": [{
            "alert_uid": a.alert_uid, "transaction_uid": a.transaction_uid, "account_uid": a.account_uid,
            "reason": a.reason, "fraud_score": a.fraud_score, "risk_level": a.risk_level,
            "status": a.status, "created_at": a.created_at.isoformat() if a.created_at else None,
        } for a in alerts],
        "cases": [{
            "case_uid": c.case_uid, "alert_uid": c.alert_uid, "status": c.status,
            "assigned_to": c.assigned_to, "final_decision": c.final_decision,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        } for c in cases],
        "status_history": [fraud_review.serialize_event(e) for e in events],
        "emails": [mailer.serialize(d) for d in emails],
        "notifications": account_notifications,
    }


@router.post("/{account_uid}/review")
def review(account_uid: str, body: ReviewRequest, background: BackgroundTasks,
           db: Session = Depends(get_db), user: User = Depends(require_fraud_analyst)):
    """Mark under review, confirm fraud (flags the account and emails the
    holder), or clear. Repeating a request that changes nothing is a no-op."""
    try:
        result = fraud_review.change_review_status(
            db, account_uid, body.action, user, note=body.note, transaction_uid=body.transaction_uid)
    except LookupError:
        raise HTTPException(status_code=404, detail="Account not found")
    except fraud_review.ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result.email is not None and result.email.status == EMAIL_PENDING:
        background.add_task(mailer.deliver, result.email.id)   # after the response; the change is saved
    return {
        "changed": result.changed,
        "message": result.message,
        "account": AccountOut.model_validate(result.account),
        "event": fraud_review.serialize_event(result.event) if result.event else None,
        "email": mailer.serialize(result.email) if result.email else None,
    }


@router.post("/{account_uid}/emails/{delivery_id}/retry")
def retry_email(account_uid: str, delivery_id: int, background: BackgroundTasks,
                db: Session = Depends(get_db)):
    delivery = db.get(EmailDelivery, delivery_id)
    if delivery is None or delivery.account_uid != account_uid:
        raise HTTPException(status_code=404, detail="Email not found")
    if delivery.status == EMAIL_SENT:
        raise HTTPException(status_code=409, detail="This email was already sent.")
    reason = mailer.no_longer_applies(db, delivery)   # e.g. the account was cleared since
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    if not mailer.claim_for_retry(db, delivery):
        raise HTTPException(status_code=409, detail="This email is being sent right now.")
    background.add_task(mailer.deliver, delivery.id)
    return mailer.serialize(delivery)

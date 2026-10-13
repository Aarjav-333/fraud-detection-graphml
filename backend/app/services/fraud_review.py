"""Manual fraud review: an analyst marks an account Under Review, confirms it
as fraud, or clears it.

This is the only way an account becomes "Confirmed Fraud" - the ML scores and
rule hits only make it Suspicious. Every change is recorded in
account_status_events (who, when, why, which transaction). Confirming queues
the account-holder email in the same database transaction, so a confirmation
always has exactly one email record, and repeating a confirmation (or two
analysts confirming at once) changes nothing and sends nothing.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.account import Account, REVIEW_UNDER_REVIEW, REVIEW_CONFIRMED_FRAUD
from app.models.account_status_event import AccountStatusEvent
from app.models.email_delivery import EmailDelivery
from app.models.transaction import Transaction
from app.models.user import User
from app.services import mailer

# action -> (the review status it sets, the statuses it may start from)
ACTIONS = {
    "under_review": (REVIEW_UNDER_REVIEW, (None,)),
    "confirm_fraud": (REVIEW_CONFIRMED_FRAUD, (None, REVIEW_UNDER_REVIEW)),
    "clear": (None, (REVIEW_UNDER_REVIEW, REVIEW_CONFIRMED_FRAUD)),
}


class ReviewError(ValueError):
    """The change isn't allowed from the account's current status, or the request is incomplete."""


@dataclass
class ReviewResult:
    account: Account
    changed: bool
    event: AccountStatusEvent | None = None
    email: EmailDelivery | None = None

    @property
    def message(self) -> str:
        status = self.account.review_status
        if not self.changed:
            return f"No change: the account is already {status or 'not under review'}."
        if status == REVIEW_CONFIRMED_FRAUD:
            return "Account confirmed as fraud and flagged."
        if status == REVIEW_UNDER_REVIEW:
            return "Account marked as under review."
        return "Review cleared: the account is no longer flagged."


def _has_status(status):
    return Account.review_status.is_(None) if status is None else Account.review_status == status


def change_review_status(db: Session, account_uid: str, action: str, user: User,
                         note: str = "", transaction_uid: str | None = None) -> ReviewResult:
    if action not in ACTIONS:
        raise ReviewError(f"Unknown action {action!r}.")
    target, allowed_from = ACTIONS[action]
    account = db.query(Account).filter_by(account_uid=account_uid).first()
    if account is None:
        raise LookupError("Account not found")
    current = account.review_status
    if current == target:
        return ReviewResult(account, changed=False)   # e.g. confirming an account already confirmed
    if current not in allowed_from:
        raise ReviewError(f"The account is {current}; clear that first to mark it under review."
                          if action == "under_review" else
                          f"Can't do that while the account is {current or 'not under review'}.")
    note = (note or "").strip()
    if action == "clear" and not note:
        raise ReviewError("Give a reason for clearing the review.")
    if transaction_uid:
        txn = db.query(Transaction).filter_by(txn_uid=transaction_uid).first()
        if txn is None or account_uid not in (txn.sender_uid, txn.receiver_uid):
            raise ReviewError(f"Transaction {transaction_uid} isn't one of this account's transactions.")

    now = datetime.utcnow()
    values = {"review_status": target, "review_updated_at": now}
    if target == REVIEW_CONFIRMED_FRAUD:
        values.update(fraud_confirmed_by=user.username, fraud_confirmed_at=now)
    elif action == "clear":
        values.update(fraud_confirmed_by=None, fraud_confirmed_at=None)
    # Conditional on the exact status we read: if another analyst changed it
    # meanwhile, nothing is overwritten and the history stays truthful. Of two
    # analysts confirming at once, only one changes the row (and sends the email).
    updated = (db.query(Account)
                 .filter(Account.account_uid == account_uid, _has_status(current))
                 .update(values, synchronize_session=False))
    if updated == 0:
        db.rollback()
        db.refresh(account)
        if account.review_status == target:
            return ReviewResult(account, changed=False)
        raise ReviewError(f"Another analyst changed this account to {account.review_status or 'not under review'} "
                          "while you were reviewing it. Check the latest status and try again.")

    event = AccountStatusEvent(
        account_uid=account_uid, from_status=current, to_status=target,
        changed_by=user.username, changed_by_id=user.id, note=note or None,
        transaction_uid=transaction_uid or None, created_at=now,
    )
    db.add(event)
    db.flush()   # event.id, for the email record
    db.refresh(account)
    email = (mailer.queue_fraud_confirmation(db, account, event, user.username)
             if target == REVIEW_CONFIRMED_FRAUD else None)
    db.commit()
    db.refresh(account)
    return ReviewResult(account, changed=True, event=event, email=email)


def serialize_event(e: AccountStatusEvent) -> dict:
    return {
        "id": e.id,
        "from_status": e.from_status,
        "to_status": e.to_status,
        "changed_by": e.changed_by,
        "note": e.note,
        "transaction_uid": e.transaction_uid,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }

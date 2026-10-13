"""Email to account holders: the notice sent when an analyst confirms their
account as fraudulent.

Only a manual confirmation queues it (see app/services/fraud_review.py), never
an ML score. Each email is logged in email_deliveries - one per confirmation,
so repeating a confirmation can't send it twice - and sent after the
confirmation is saved, so a mail problem never undoes the status change.
Temporary failures (the server unreachable, a 4xx reply) are retried; the log
keeps every attempt's outcome, and a failed email can be retried later.
SMTP settings come from the environment (app/config.py).
"""
import html
import logging
import re
import smtplib
import ssl
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.core.formatting import format_inr, format_timestamp
from app.database import SessionLocal
from app.models.account import Account, REVIEW_CONFIRMED_FRAUD
from app.models.account_status_event import AccountStatusEvent
from app.models.email_delivery import (
    EmailDelivery, EMAIL_PENDING, EMAIL_SENT, EMAIL_FAILED, EMAIL_SKIPPED,
)
from app.models.transaction import Transaction

log = logging.getLogger(__name__)

KIND_FRAUD_CONFIRMATION = "fraud_confirmation"
SUBJECT = "Important Security Alert – Your Account Has Been Flagged"
RETRY_DELAYS = (2, 6)          # seconds to wait before the 2nd and 3rd attempt
STALE_PENDING = timedelta(minutes=10)   # a "pending" email this old was interrupted
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Reserved for documentation and testing (RFC 2606 / 6761); mail to them can't arrive
_RESERVED_DOMAINS = ("example.com", "example.net", "example.org")
_RESERVED_SUFFIXES = (".example", ".test", ".invalid", ".localhost")


class PermanentEmailError(Exception):
    """A failure that retrying won't fix (rejected address, bad credentials, no SMTP setup)."""


def mask_account(account_uid: str) -> str:
    """'ACC01023' -> 'XXXX1023'."""
    return "X" * max(len(account_uid) - 4, 4) + account_uid[-4:]


def mask_email(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    local, domain = address.rsplit("@", 1)
    return f"{local[:1]}***@{domain}"


def undeliverable_reason(address: str | None) -> str | None:
    """Why an email to this address can't be delivered, or None if it can be tried."""
    if not address or not address.strip():
        return "The account has no registered email address."
    address = address.strip()
    if not _ADDRESS.match(address):
        return "The registered email address is not valid."
    domain = address.rsplit("@", 1)[1].lower()
    if domain in _RESERVED_DOMAINS or domain.endswith(_RESERVED_SUFFIXES) \
            or any(domain.endswith("." + d) for d in _RESERVED_DOMAINS):
        return f"The registered address uses {domain}, a domain reserved for testing that can't receive mail."
    return None


def queue_fraud_confirmation(db: Session, account: Account, event: AccountStatusEvent,
                             requested_by: str) -> EmailDelivery:
    """Log the email for this confirmation, in the caller's transaction. It is
    pending (deliver() sends it once the caller has committed), or skipped if
    the account has no usable address."""
    reason = undeliverable_reason(account.email)
    delivery = EmailDelivery(
        kind=KIND_FRAUD_CONFIRMATION,
        account_uid=account.account_uid,
        status_event_id=event.id,
        recipient_masked=mask_email(account.email),
        subject=SUBJECT,
        status=EMAIL_SKIPPED if reason else EMAIL_PENDING,
        last_error=reason,
        requested_by=requested_by,
        created_at=datetime.utcnow(),
    )
    db.add(delivery)
    return delivery


# ------------------------------------------------------------------ the message

def build_fraud_confirmation(account: Account, txn: Transaction | None) -> EmailMessage:
    name = account.customer_name or "Customer"
    details = [("Account Reference", mask_account(account.account_uid))]
    if txn is not None:
        details += [("Transaction Reference", txn.txn_uid),
                    ("Transaction Date", format_timestamp(txn.timestamp)),
                    ("Transaction Amount", format_inr(txn.amount))]
    details.append(("Account Status", "Flagged for Fraudulent Activity"))
    support = settings.EMAIL_SUPPORT_CONTACT.strip()
    contact = ("If you believe this action was taken in error or you do not recognize the transaction, "
               "please contact our support team using the official support channel.")

    text = "\n".join([
        f"Dear {name},",
        "",
        "We are writing to inform you that your account has been flagged following a review of "
        "potentially fraudulent transaction activity.",
        "",
        "Account Information:",
        *[f"  {label}: {value}" for label, value in details],
        "",
        "Our fraud monitoring system identified suspicious transaction activity, which was "
        "subsequently reviewed and confirmed by our fraud analysis team.",
        "",
        contact + (f"\nSupport: {support}" if support else ""),
        "",
        "This notification has been generated automatically by our Fraud Detection and Monitoring System.",
        "",
        "Regards,",
        settings.EMAIL_FROM_NAME or "Fraud Monitoring Team",
    ])

    e = html.escape
    rows = "".join(
        f'<tr><td style="padding:6px 16px 6px 0;color:#6b7280;white-space:nowrap">{e(label)}</td>'
        f'<td style="padding:6px 0;color:#111827;font-weight:600">{e(value)}</td></tr>'
        for label, value in details)
    support_html = (f'<p style="margin:0 0 16px">Support: {e(support)}</p>' if support else "")
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{e(SUBJECT)}</title></head>
<body style="margin:0;padding:24px;background:#f5f6f8;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#111827">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;border:1px solid #e5e7eb">
<tr><td style="padding:20px 28px;border-bottom:3px solid #dc2626;font-size:18px;font-weight:700">Important Security Alert</td></tr>
<tr><td style="padding:24px 28px">
<p style="margin:0 0 16px">Dear {e(name)},</p>
<p style="margin:0 0 16px">We are writing to inform you that your account has been flagged following a review of potentially fraudulent transaction activity.</p>
<p style="margin:0 0 8px;font-weight:700">Account Information</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 16px">{rows}</table>
<p style="margin:0 0 16px">Our fraud monitoring system identified suspicious transaction activity, which was subsequently reviewed and confirmed by our fraud analysis team.</p>
<p style="margin:0 0 16px">{e(contact)}</p>
{support_html}<p style="margin:0 0 16px;color:#6b7280;font-size:13px">This notification has been generated automatically by our Fraud Detection and Monitoring System.</p>
<p style="margin:0">Regards,<br>{e(settings.EMAIL_FROM_NAME or "Fraud Monitoring Team")}</p>
</td></tr></table></body></html>"""

    msg = EmailMessage()
    msg["Subject"] = SUBJECT
    msg["From"] = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM))
    msg["To"] = account.email.strip()
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=settings.EMAIL_FROM.rsplit("@", 1)[-1] or None)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text)
    msg.add_alternative(body, subtype="html")
    return msg


# ------------------------------------------------------------------ sending

def _send(message: EmailMessage) -> None:
    if not settings.SMTP_HOST or not settings.EMAIL_FROM:
        raise PermanentEmailError("Email is not configured: set SMTP_HOST and EMAIL_FROM on the backend.")
    security = settings.SMTP_SECURITY   # starttls / ssl / none, checked when the settings load
    smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    kwargs = {"context": ssl.create_default_context()} if security == "ssl" else {}
    try:
        with smtp_class(settings.SMTP_HOST, settings.SMTP_PORT,
                        timeout=settings.SMTP_TIMEOUT_SECONDS, **kwargs) as smtp:
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused,
            smtplib.SMTPNotSupportedError) as exc:
        raise PermanentEmailError(_describe(exc)) from exc
    except smtplib.SMTPResponseException as exc:
        if exc.smtp_code >= 500:   # 5xx: the server refuses for good; 4xx: try again later
            raise PermanentEmailError(_describe(exc)) from exc
        raise


def _describe(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The mail server refused the recipient address."
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "The mail server rejected the SMTP username or password."
    if isinstance(exc, smtplib.SMTPResponseException):
        reply = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        return f"Mail server replied {exc.smtp_code}: {reply}"[:500]
    return f"{type(exc).__name__}: {exc}"[:500]


def no_longer_applies(db: Session, delivery: EmailDelivery) -> str | None:
    """Why this confirmation email must not be sent (any more), or None. It
    applies only while the account is still Confirmed Fraud by the very
    decision that queued it - not after it was cleared, or re-confirmed later
    (that confirmation has its own email). Reads the database directly, since
    another analyst may have changed the account meanwhile."""
    status = db.query(Account.review_status).filter_by(account_uid=delivery.account_uid).first()
    if status is None:
        return "The account no longer exists, so the email was not sent."
    if status[0] != REVIEW_CONFIRMED_FRAUD:
        return "The account is no longer flagged as fraud, so the email was not sent."
    latest = (db.query(AccountStatusEvent.id).filter_by(account_uid=delivery.account_uid)
                .order_by(AccountStatusEvent.id.desc()).first())
    if latest is None or latest[0] != delivery.status_event_id:
        return "A later review decision replaced this confirmation, so the email was not sent."
    return None


def deliver(delivery_id: int) -> None:
    """Send a pending email, retrying temporary failures. Runs after the
    request that queued it has returned (a background task), with its own
    database session, and records the outcome of every attempt."""
    db = SessionLocal()
    try:
        delivery = db.get(EmailDelivery, delivery_id)
        if delivery is None or delivery.status != EMAIL_PENDING:
            return
        account = db.query(Account).filter_by(account_uid=delivery.account_uid).first()
        event = db.get(AccountStatusEvent, delivery.status_event_id) if delivery.status_event_id else None
        reason = undeliverable_reason(account.email if account else None)
        if account is None or reason:
            delivery.status, delivery.last_error = EMAIL_SKIPPED, reason or "The account no longer exists."
            db.commit()
            return
        txn = (db.query(Transaction).filter_by(txn_uid=event.transaction_uid).first()
               if event is not None and event.transaction_uid else None)
        delivery.recipient_masked = mask_email(account.email)
        message = build_fraud_confirmation(account, txn)

        attempts = len(RETRY_DELAYS) + 1
        for attempt in range(1, attempts + 1):
            stale = no_longer_applies(db, delivery)   # checked again before every attempt
            if stale:
                delivery.status, delivery.last_error = EMAIL_SKIPPED, stale
                db.commit()
                return
            delivery.attempts = (delivery.attempts or 0) + 1
            delivery.last_attempt_at = datetime.utcnow()
            try:
                _send(message)
            except PermanentEmailError as exc:
                delivery.status, delivery.last_error = EMAIL_FAILED, str(exc)
                db.commit()
                log.warning("Email %s to %s failed: %s", delivery.id, delivery.account_uid, exc)
                return
            except (OSError, smtplib.SMTPException) as exc:   # unreachable, timed out, 4xx...
                delivery.last_error = _describe(exc)
                if attempt == attempts:
                    delivery.status = EMAIL_FAILED
                    db.commit()
                    log.warning("Email %s to %s failed after %d attempts: %s",
                                delivery.id, delivery.account_uid, attempt, delivery.last_error)
                    return
                db.commit()
                time.sleep(RETRY_DELAYS[attempt - 1])
            else:
                delivery.status, delivery.sent_at, delivery.last_error = EMAIL_SENT, datetime.utcnow(), None
                db.commit()
                return
    except Exception:
        log.exception("Email delivery %s crashed", delivery_id)
        db.rollback()
        delivery = db.get(EmailDelivery, delivery_id)
        if delivery is not None and delivery.status == EMAIL_PENDING:
            delivery.status, delivery.last_error = EMAIL_FAILED, "Unexpected error while sending; retry it."
            db.commit()
    finally:
        db.close()


def claim_for_retry(db: Session, delivery: EmailDelivery) -> bool:
    """Put a failed, skipped or interrupted email back to pending, so it can be
    sent again. False if it can't be retried (sent, or being sent right now)."""
    stale = datetime.utcnow() - STALE_PENDING
    claimed = (db.query(EmailDelivery)
                 .filter(EmailDelivery.id == delivery.id,
                         or_(EmailDelivery.status.in_([EMAIL_FAILED, EMAIL_SKIPPED]),
                             and_(EmailDelivery.status == EMAIL_PENDING,
                                  func.coalesce(EmailDelivery.last_attempt_at,
                                                EmailDelivery.created_at) < stale)))
                 .update({"status": EMAIL_PENDING, "last_error": None, "last_attempt_at": datetime.utcnow()},
                         synchronize_session=False))
    db.commit()
    db.refresh(delivery)
    return claimed == 1


def serialize(d: EmailDelivery) -> dict:
    return {
        "id": d.id,
        "kind": d.kind,
        "status": d.status,
        "recipient": d.recipient_masked,
        "subject": d.subject,
        "attempts": d.attempts,
        "last_error": d.last_error,
        "requested_by": d.requested_by,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
    }

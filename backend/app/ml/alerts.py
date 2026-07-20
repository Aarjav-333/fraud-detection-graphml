"""Fraud alert generation (workflow Step 11).

Creates alerts from two upstream signals:
  RULE  : transactions marked status='suspicious' by the rule engine
  ML    : accounts whose fraud_score >= threshold (from the baseline models)

Generation is idempotent and non-destructive: alerts already raised for a
transaction/account are kept (including any status the admin has set), and
only new ones are added.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.transaction import Transaction
from app.models.account import Account

ALERT_STATUSES = ["Pending", "Under Review", "Confirmed Fraud", "False Positive", "Resolved"]


def _next_alert_num(db: Session) -> int:
    last = db.query(Alert.alert_uid).order_by(Alert.id.desc()).first()
    if last and last[0] and last[0].startswith("ALT"):
        try:
            return int(last[0][3:]) + 1
        except ValueError:
            pass
    return 1


def _score_to_risk(score: float) -> str:
    if score >= 0.8:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def generate(db: Session, ml_threshold: float = 0.8) -> dict:
    num = _next_alert_num(db)
    created_rule, created_ml = 0, 0

    # --- RULE alerts: one per suspicious transaction that has no alert yet ---
    existing_txn = {uid for (uid,) in db.query(Alert.transaction_uid)
                    .filter(Alert.transaction_uid.isnot(None)).all()}
    suspicious = (db.query(Transaction)
                    .filter(Transaction.status == "suspicious").all())
    acc_scores = dict(db.query(Account.account_uid, Account.fraud_score).all())

    new_alerts = []
    for t in suspicious:
        if t.txn_uid in existing_txn:
            continue
        score = max(acc_scores.get(t.sender_uid, 0.0) or 0.0,
                    acc_scores.get(t.receiver_uid, 0.0) or 0.0)
        new_alerts.append(dict(
            alert_uid=f"ALT{num:06d}",
            transaction_uid=t.txn_uid,
            account_uid=t.receiver_uid,   # money destination is the natural suspect
            reason="Rule engine: transaction matched suspicious pattern",
            fraud_score=round(float(score), 4),
            risk_level=_score_to_risk(score),
            status="Pending",
            created_at=datetime.utcnow(),
        ))
        num += 1
        created_rule += 1

    # --- ML alerts: one per high-score account that has no account-level alert yet ---
    existing_acc = {uid for (uid,) in db.query(Alert.account_uid)
                    .filter(Alert.transaction_uid.is_(None)).all()}
    risky = (db.query(Account)
               .filter(Account.fraud_score >= ml_threshold).all())
    for a in risky:
        if a.account_uid in existing_acc:
            continue
        new_alerts.append(dict(
            alert_uid=f"ALT{num:06d}",
            transaction_uid=None,
            account_uid=a.account_uid,
            reason=f"ML model: account fraud score {a.fraud_score:.2f} >= {ml_threshold:.2f}",
            fraud_score=round(float(a.fraud_score), 4),
            risk_level=_score_to_risk(a.fraud_score),
            status="Pending",
            created_at=datetime.utcnow(),
        ))
        num += 1
        created_ml += 1

    for i in range(0, len(new_alerts), 500):
        db.bulk_insert_mappings(Alert, new_alerts[i:i + 500])
    db.commit()

    return {
        "created_rule_alerts": created_rule,
        "created_ml_alerts": created_ml,
        "total_alerts": db.query(Alert).count(),
        "ml_threshold": ml_threshold,
    }


def summary(db: Session) -> dict:
    counts = {s: 0 for s in ALERT_STATUSES}
    for status, in db.query(Alert.status).all():
        if status in counts:
            counts[status] += 1
    by_risk = {"High": 0, "Medium": 0, "Low": 0}
    for risk, in db.query(Alert.risk_level).all():
        if risk in by_risk:
            by_risk[risk] += 1
    return {"total": db.query(Alert).count(), "by_status": counts, "by_risk": by_risk}

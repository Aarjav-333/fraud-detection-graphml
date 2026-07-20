"""Dashboard aggregates (workflow Step 14 — monitoring view)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.alert import Alert
from app.models.case import Case
from app.ml.fraud_ring import load_rings
from app.ml.baseline import load_results

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    # --- accounts ---
    total_accounts = db.query(Account).count()
    risk_counts = dict(
        db.query(Account.risk_level, func.count()).group_by(Account.risk_level).all()
    )

    # --- transactions ---
    total_txns = db.query(Transaction).count()
    suspicious_txns = db.query(Transaction).filter(Transaction.status == "suspicious").count()
    total_volume = db.query(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    suspicious_volume = (db.query(func.coalesce(func.sum(Transaction.amount), 0))
                           .filter(Transaction.status == "suspicious").scalar())

    # --- alerts ---
    total_alerts = db.query(Alert).count()
    alert_status = dict(db.query(Alert.status, func.count()).group_by(Alert.status).all())

    # --- cases ---
    total_cases = db.query(Case).count()
    case_status = dict(db.query(Case.status, func.count()).group_by(Case.status).all())
    open_cases = case_status.get("Open", 0) + case_status.get("Under Investigation", 0)

    # --- rings + ML (from caches; None-safe) ---
    rings = load_rings()
    ml = load_results()

    # --- daily transaction series, last 30 days of data ---
    last_ts = db.query(func.max(Transaction.timestamp)).scalar()
    daily = []
    if last_ts:
        start = last_ts - timedelta(days=29)
        rows = (db.query(
                    func.date(Transaction.timestamp),
                    func.count(),
                    func.sum(case((Transaction.status == "suspicious", 1), else_=0)),
                )
                .filter(Transaction.timestamp >= start)
                .group_by(func.date(Transaction.timestamp))
                .order_by(func.date(Transaction.timestamp))
                .all())
        daily = [{"date": str(d), "transactions": int(n), "suspicious": int(s or 0)} for d, n, s in rows]

    # --- recent high-risk accounts ---
    top_accounts = (db.query(Account)
                      .filter(Account.risk_level == "High")
                      .order_by(Account.fraud_score.desc())
                      .limit(6).all())

    return {
        "accounts": {
            "total": total_accounts,
            "high_risk": risk_counts.get("High", 0),
            "medium_risk": risk_counts.get("Medium", 0),
            "low_risk": risk_counts.get("Low", 0),
        },
        "transactions": {
            "total": total_txns,
            "suspicious": suspicious_txns,
            "total_volume": round(float(total_volume), 2),
            "suspicious_volume": round(float(suspicious_volume), 2),
        },
        "alerts": {"total": total_alerts, "by_status": alert_status},
        "cases": {"total": total_cases, "open": open_cases, "by_status": case_status},
        "rings": {
            "found": rings["rings_found"] if rings else 0,
            "accounts_involved": rings["accounts_involved"] if rings else 0,
        },
        "ml": {
            "trained": ml is not None,
            "best_model": ml.get("best_model") if ml else None,
            "best_f1": (ml["results"][ml["best_model"]]["f1"] if ml else None),
        },
        "daily_transactions": daily,
        "top_risk_accounts": [
            {"account_uid": a.account_uid, "customer_name": a.customer_name,
             "fraud_score": a.fraud_score, "risk_level": a.risk_level}
            for a in top_accounts
        ],
    }

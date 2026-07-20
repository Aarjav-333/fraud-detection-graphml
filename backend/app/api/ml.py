from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.ml import baseline
from app.models.account import Account

router = APIRouter(prefix="/api/ml", tags=["ml"], dependencies=[Depends(get_current_user)])


@router.post("/train")
def train(db: Session = Depends(get_db)):
    try:
        return baseline.train_and_score(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/status")
def status():
    res = baseline.load_results()
    return {"has_run": res is not None, "results": res}


@router.get("/top-risk")
def top_risk(limit: int = Query(15, le=100), db: Session = Depends(get_db)):
    rows = (db.query(Account)
              .order_by(Account.fraud_score.desc())
              .limit(limit).all())
    return [
        {
            "account_uid": r.account_uid, "customer_name": r.customer_name,
            "fraud_score": r.fraud_score, "risk_level": r.risk_level,
            "is_fraud": r.is_fraud,
        }
        for r in rows
    ]

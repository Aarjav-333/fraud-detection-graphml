from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models.alert import Alert
from app.ml import alerts as alert_engine

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_user)])


class GenerateRequest(BaseModel):
    ml_threshold: float = Field(0.8, ge=0.5, le=0.99)


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(Pending|Under Review|Confirmed Fraud|False Positive|Resolved)$")


@router.post("/generate")
def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    return alert_engine.generate(db, ml_threshold=req.ml_threshold)


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    return alert_engine.summary(db)


@router.get("")
def list_alerts(
    skip: int = 0,
    limit: int = Query(25, le=200),
    status: Optional[str] = None,
    risk: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Alert)
    if status:
        query = query.filter(Alert.status == status)
    if risk:
        query = query.filter(Alert.risk_level == risk)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Alert.alert_uid.ilike(like),
            Alert.account_uid.ilike(like),
            Alert.transaction_uid.ilike(like),
        ))
    total = query.count()
    items = query.order_by(Alert.fraud_score.desc(), Alert.id.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "alert_uid": a.alert_uid, "transaction_uid": a.transaction_uid,
                "account_uid": a.account_uid, "reason": a.reason,
                "fraud_score": a.fraud_score, "risk_level": a.risk_level,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "type": "Transaction" if a.transaction_uid else "Account",
            }
            for a in items
        ],
    }


@router.put("/{alert_uid}/status")
def update_status(alert_uid: str, body: StatusUpdate, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.alert_uid == alert_uid).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = body.status
    db.commit()
    return {"alert_uid": alert_uid, "status": alert.status}

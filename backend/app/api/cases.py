"""Investigation case management (workflow Step 13)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.case import Case
from app.models.alert import Alert
from app.models.account import Account

router = APIRouter(prefix="/api/cases", tags=["cases"], dependencies=[Depends(get_current_user)])

CASE_STATUSES = ["Open", "Under Investigation", "Confirmed Fraud", "False Positive", "Closed"]


class CaseCreate(BaseModel):
    account_uid: str
    alert_uid: Optional[str] = None
    assigned_to: str = Field("", max_length=100)
    notes: str = Field("", max_length=5000)


class CaseUpdate(BaseModel):
    assigned_to: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=5000)
    status: Optional[str] = Field(None, pattern="^(Open|Under Investigation|Confirmed Fraud|False Positive|Closed)$")
    final_decision: Optional[str] = Field(None, max_length=500)


def _next_case_uid(db: Session) -> str:
    last = db.query(Case.case_uid).order_by(Case.id.desc()).first()
    if last and last[0] and last[0].startswith("CASE"):
        try:
            return f"CASE{int(last[0][4:]) + 1:05d}"
        except ValueError:
            pass
    return "CASE00001"


def _serialize(c: Case) -> dict:
    return {
        "case_uid": c.case_uid, "alert_uid": c.alert_uid, "account_uid": c.account_uid,
        "notes": c.notes or "", "assigned_to": c.assigned_to or "",
        "status": c.status, "final_decision": c.final_decision or "",
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    counts = {s: 0 for s in CASE_STATUSES}
    for (status,) in db.query(Case.status).all():
        if status in counts:
            counts[status] += 1
    return {"total": db.query(Case).count(), "by_status": counts}


@router.get("")
def list_cases(
    skip: int = 0,
    limit: int = Query(25, le=200),
    status: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Case)
    if status:
        query = query.filter(Case.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Case.case_uid.ilike(like), Case.account_uid.ilike(like),
            Case.alert_uid.ilike(like), Case.assigned_to.ilike(like),
        ))
    total = query.count()
    items = query.order_by(Case.id.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [_serialize(c) for c in items]}


@router.get("/{case_uid}")
def get_case(case_uid: str, db: Session = Depends(get_db)):
    c = db.query(Case).filter(Case.case_uid == case_uid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    data = _serialize(c)
    account = db.query(Account).filter(Account.account_uid == c.account_uid).first()
    if account:
        data["account"] = {
            "customer_name": account.customer_name, "risk_level": account.risk_level,
            "fraud_score": account.fraud_score, "is_active": account.is_active,
        }
    if c.alert_uid:
        alert = db.query(Alert).filter(Alert.alert_uid == c.alert_uid).first()
        if alert:
            data["alert"] = {
                "reason": alert.reason, "fraud_score": alert.fraud_score,
                "risk_level": alert.risk_level, "status": alert.status,
                "transaction_uid": alert.transaction_uid,
            }
    return data


@router.post("", status_code=201)
def create_case(body: CaseCreate, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.account_uid == body.account_uid).first()
    if not account:
        raise HTTPException(status_code=400, detail=f"Account '{body.account_uid}' does not exist")
    if body.alert_uid:
        alert = db.query(Alert).filter(Alert.alert_uid == body.alert_uid).first()
        if not alert:
            raise HTTPException(status_code=400, detail=f"Alert '{body.alert_uid}' does not exist")
        # opening a case implies the alert is being investigated
        if alert.status == "Pending":
            alert.status = "Under Review"
    c = Case(
        case_uid=_next_case_uid(db),
        alert_uid=body.alert_uid,
        account_uid=body.account_uid,
        notes=body.notes,
        assigned_to=body.assigned_to,
        status="Open",
        final_decision=None,
        created_at=datetime.utcnow(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _serialize(c)


@router.put("/{case_uid}")
def update_case(case_uid: str, body: CaseUpdate, db: Session = Depends(get_db)):
    c = db.query(Case).filter(Case.case_uid == case_uid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    if body.assigned_to is not None:
        c.assigned_to = body.assigned_to
    if body.notes is not None:
        c.notes = body.notes
    if body.final_decision is not None:
        c.final_decision = body.final_decision
    if body.status is not None:
        c.status = body.status
        # closing decisions propagate to the linked alert
        if c.alert_uid and body.status in ("Confirmed Fraud", "False Positive"):
            alert = db.query(Alert).filter(Alert.alert_uid == c.alert_uid).first()
            if alert:
                alert.status = body.status
    db.commit()
    return _serialize(c)


@router.delete("/{case_uid}")
def delete_case(case_uid: str, db: Session = Depends(get_db)):
    c = db.query(Case).filter(Case.case_uid == case_uid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    db.delete(c)
    db.commit()
    return {"deleted": case_uid}

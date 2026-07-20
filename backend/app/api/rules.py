from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.ml import rules as rules_engine
from app.models.transaction import Transaction

router = APIRouter(prefix="/api/rules", tags=["rules"], dependencies=[Depends(get_current_user)])


@router.post("/run")
def run(db: Session = Depends(get_db)):
    return rules_engine.apply_rules(db)


@router.get("/status")
def status(db: Session = Depends(get_db)):
    suspicious = db.query(Transaction).filter(Transaction.status == "suspicious").count()
    total = db.query(Transaction).count()
    return {"total_transactions": total, "total_suspicious": suspicious,
            "has_run": suspicious > 0}

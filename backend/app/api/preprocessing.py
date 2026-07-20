from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.ml import preprocessing

router = APIRouter(prefix="/api/preprocessing", tags=["preprocessing"],
                   dependencies=[Depends(get_current_user)])


@router.get("/report")
def report(db: Session = Depends(get_db)):
    return preprocessing.analyze(db)


@router.post("/clean")
def clean(db: Session = Depends(get_db)):
    return preprocessing.clean(db)

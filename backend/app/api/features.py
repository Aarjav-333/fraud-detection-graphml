from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.ml import features as feat

router = APIRouter(prefix="/api/features", tags=["features"], dependencies=[Depends(get_current_user)])


@router.post("/build")
def build(db: Session = Depends(get_db)):
    return feat.build_and_save(db)


@router.get("/status")
def status():
    df = feat.load_features()
    if df is None:
        return {"has_run": False}
    return {
        "has_run": True,
        "accounts": int(len(df)),
        "fraud_accounts": int(df["is_fraud"].sum()),
        "fraud_ratio": round(float(df["is_fraud"].mean()), 4),
        "feature_list": [
            {"name": k, "description": v} for k, v in feat.FEATURE_DESCRIPTIONS.items()
        ],
    }


@router.get("/preview")
def preview(
    limit: int = Query(12, le=50),
    fraud_only: bool = False,
):
    df = feat.load_features()
    if df is None:
        raise HTTPException(status_code=404, detail="Features not built yet. Run build first.")
    if fraud_only:
        df = df[df["is_fraud"] == 1]
    return df.head(limit).to_dict(orient="records")

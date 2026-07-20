from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.ml import fraud_ring

router = APIRouter(prefix="/api/rings", tags=["rings"], dependencies=[Depends(get_current_user)])


@router.post("/detect")
def detect(db: Session = Depends(get_db)):
    return {k: v for k, v in fraud_ring.detect(db).items() if k != "rings"} | {
        "rings": [
            {k: v for k, v in r.items() if k not in ("nodes", "links")}
            for r in fraud_ring.load_rings()["rings"]
        ]
    }


@router.get("/status")
def status():
    data = fraud_ring.load_rings()
    if data is None:
        return {"has_run": False}
    return {"has_run": True,
            "rings_found": data["rings_found"],
            "accounts_involved": data["accounts_involved"],
            "total_flow": data["total_flow"],
            "high_risk_rings": data["high_risk_rings"],
            "rings": [
                {k: v for k, v in r.items() if k not in ("nodes", "links")}
                for r in data["rings"]
            ]}


@router.get("/{ring_id}")
def get_ring(ring_id: str):
    data = fraud_ring.load_rings()
    if data is None:
        raise HTTPException(status_code=404, detail="Rings not detected yet")
    for r in data["rings"]:
        if r["ring_id"] == ring_id:
            return r
    raise HTTPException(status_code=404, detail=f"Ring '{ring_id}' not found")

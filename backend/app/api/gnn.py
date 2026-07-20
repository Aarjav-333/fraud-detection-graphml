from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.ml import gnn

router = APIRouter(prefix="/api/gnn", tags=["gnn"], dependencies=[Depends(get_current_user)])


class TrainRequest(BaseModel):
    source: str = Field("synthetic", pattern="^(synthetic|elliptic)$")
    model: str = Field("graphsage", pattern="^(gcn|graphsage)$")
    epochs: int = Field(100, ge=10, le=500)


@router.post("/train")
def train(req: TrainRequest, db: Session = Depends(get_db)):
    try:
        return gnn.train(db, source=req.source, model_type=req.model, epochs=req.epochs)
    except gnn.GNNDepsMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/status")
def status():
    deps_ok = True
    try:
        gnn._require_torch()
    except gnn.GNNDepsMissing:
        deps_ok = False
    return {"deps_installed": deps_ok, "results": gnn.load_results()}

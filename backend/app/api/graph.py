from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.ml import graph_analysis
from app.models.graph_metric import GraphMetric

router = APIRouter(prefix="/api/graph", tags=["graph"], dependencies=[Depends(get_current_user)])


@router.post("/analyze")
def analyze(db: Session = Depends(get_db)):
    return graph_analysis.analyze(db)


@router.get("/status")
def status(db: Session = Depends(get_db)):
    count = db.query(GraphMetric).count()
    return {"has_run": count > 0, "accounts_analyzed": count}


@router.get("/metrics")
def metrics(
    sort_by: str = Query("pagerank", pattern="^(pagerank|degree_centrality|in_degree|out_degree|total_received|total_sent)$"),
    limit: int = Query(15, le=100),
    in_cycle_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(GraphMetric)
    if in_cycle_only:
        q = q.filter(GraphMetric.in_cycle == 1)
    col = getattr(GraphMetric, sort_by)
    rows = q.order_by(col.desc()).limit(limit).all()
    return [
        {
            "account_uid": r.account_uid, "in_degree": r.in_degree, "out_degree": r.out_degree,
            "total_received": r.total_received, "total_sent": r.total_sent,
            "degree_centrality": r.degree_centrality, "pagerank": r.pagerank,
            "component_size": r.component_size, "community_id": r.community_id,
            "community_size": r.community_size, "in_cycle": r.in_cycle,
        }
        for r in rows
    ]


@router.get("/neighborhood/{account_uid}")
def get_neighborhood(
    account_uid: str,
    hops: int = Query(1, ge=1, le=2),
    db: Session = Depends(get_db),
):
    result = graph_analysis.neighborhood(db, account_uid, hops=hops)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"Account '{account_uid}' not found in the graph")
    return result

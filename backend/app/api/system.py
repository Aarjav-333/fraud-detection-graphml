"""What kind of backend this is, for the frontend: the normal app, or the
standalone demo (where ML/GNN training is off). Public - it holds no data."""
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/system", tags=["system"])

ML_NEEDS_MAIN_DATASET = (
    "Model training and benchmarking need the main labelled dataset (5,000 accounts with fraud "
    "labels). The standalone demo holds only the 22 scripted accounts and transactions - far too "
    "few to train or fairly evaluate a model - so it shows how the rules, the graph analysis and "
    "ring detection catch the scenario instead.")


@router.get("/info")
def info():
    standalone = settings.is_standalone_demo
    return {
        "demo_mode": settings.DEMO_MODE or None,
        "ml_training_available": not standalone,
        "ml_unavailable_reason": ML_NEEDS_MAIN_DATASET if standalone else None,
    }

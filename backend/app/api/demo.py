"""The demo scenario's detection coverage (works in any database holding it:
the standalone demo, or the demo copy of the full dataset)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.demo import coverage

router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(get_current_user)])


@router.get("/scenario")
def scenario(db: Session = Depends(get_db)):
    data = coverage.report(db)
    if data is None:
        raise HTTPException(status_code=404, detail="The demo scenario isn't in this database. Build it with "
                                                    "python -m scripts.demo_scenario --standalone")
    return {"demo_mode": settings.DEMO_MODE or None, **data}

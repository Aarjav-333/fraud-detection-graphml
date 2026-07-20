from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.schemas.account import AccountCreate, AccountUpdate, AccountOut, AccountList
from app.crud import account as crud

router = APIRouter(prefix="/api/accounts", tags=["accounts"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=AccountList)
def list_accounts(
    skip: int = 0,
    limit: int = Query(25, le=200),
    q: Optional[str] = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    total, items = crud.list_accounts(db, skip=skip, limit=limit, q=q, active_only=active_only)
    return {"total": total, "items": items}


@router.post("", response_model=AccountOut, status_code=201)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    if data.account_uid and crud.get_account(db, data.account_uid):
        raise HTTPException(status_code=400, detail="account_uid already exists")
    return crud.create_account(db, data)


@router.get("/{account_uid}", response_model=AccountOut)
def get_account(account_uid: str, db: Session = Depends(get_db)):
    acc = crud.get_account(db, account_uid)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.put("/{account_uid}", response_model=AccountOut)
def update_account(account_uid: str, data: AccountUpdate, db: Session = Depends(get_db)):
    acc = crud.update_account(db, account_uid, data)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.post("/{account_uid}/deactivate", response_model=AccountOut)
def deactivate_account(account_uid: str, db: Session = Depends(get_db)):
    acc = crud.set_active(db, account_uid, False)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.post("/{account_uid}/activate", response_model=AccountOut)
def activate_account(account_uid: str, db: Session = Depends(get_db)):
    acc = crud.set_active(db, account_uid, True)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc

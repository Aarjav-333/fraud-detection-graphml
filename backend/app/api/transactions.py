import io
from typing import Optional
from datetime import datetime
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models.transaction import Transaction
from app.models.account import Account
from app.schemas.transaction import (
    TransactionCreate, TransactionUpdate, TransactionOut, TransactionList, UploadResult,
)
from app.crud import transaction as crud

router = APIRouter(prefix="/api/transactions", tags=["transactions"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=TransactionList)
def list_transactions(
    skip: int = 0,
    limit: int = Query(25, le=200),
    q: Optional[str] = None,
    fraud_only: bool = False,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    total, items = crud.list_transactions(db, skip=skip, limit=limit, q=q,
                                          fraud_only=fraud_only, status=status)
    return {"total": total, "items": items}


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(data: TransactionCreate, db: Session = Depends(get_db)):
    # follow the workflow rule: reject transactions referencing unknown accounts
    if not crud.account_exists(db, data.sender_uid):
        raise HTTPException(status_code=400, detail=f"Sender account '{data.sender_uid}' does not exist")
    if not crud.account_exists(db, data.receiver_uid):
        raise HTTPException(status_code=400, detail=f"Receiver account '{data.receiver_uid}' does not exist")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
    return crud.create_transaction(db, data)


@router.get("/{txn_uid}", response_model=TransactionOut)
def get_transaction(txn_uid: str, db: Session = Depends(get_db)):
    txn = crud.get_transaction(db, txn_uid)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.put("/{txn_uid}", response_model=TransactionOut)
def update_transaction(txn_uid: str, data: TransactionUpdate, db: Session = Depends(get_db)):
    txn = crud.update_transaction(db, txn_uid, data)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.delete("/{txn_uid}", status_code=204)
def delete_transaction(txn_uid: str, db: Session = Depends(get_db)):
    if not crud.delete_transaction(db, txn_uid):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return None


@router.post("/upload", response_model=UploadResult)
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bulk-upload transactions from a CSV.

    Required columns: sender_uid, receiver_uid, amount.
    Optional columns: timestamp, txn_type.
    Rows referencing unknown accounts or with invalid amounts are skipped and reported.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {exc}")

    required = {"sender_uid", "receiver_uid", "amount"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(sorted(missing))}")

    # cache known account ids once
    known = {uid for (uid,) in db.query(Account.account_uid).all()}

    inserted, skipped, errors = 0, 0, []
    next_num = int(crud.next_txn_uid(db)[3:])
    new_rows = []

    for i, row in df.iterrows():
        line = i + 2  # +1 header, +1 to 1-index
        sender = str(row.get("sender_uid", "")).strip()
        receiver = str(row.get("receiver_uid", "")).strip()
        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError):
            skipped += 1
            if len(errors) < 20:
                errors.append(f"Row {line}: invalid amount")
            continue
        if sender not in known:
            skipped += 1
            if len(errors) < 20:
                errors.append(f"Row {line}: sender '{sender}' does not exist")
            continue
        if receiver not in known:
            skipped += 1
            if len(errors) < 20:
                errors.append(f"Row {line}: receiver '{receiver}' does not exist")
            continue
        if amount <= 0:
            skipped += 1
            if len(errors) < 20:
                errors.append(f"Row {line}: amount must be > 0")
            continue

        ts = row.get("timestamp")
        try:
            ts = pd.to_datetime(ts).to_pydatetime() if pd.notna(ts) else datetime.utcnow()
        except Exception:
            ts = datetime.utcnow()

        new_rows.append({
            "txn_uid": f"TXN{next_num:07d}",
            "sender_uid": sender,
            "receiver_uid": receiver,
            "amount": amount,
            "timestamp": ts,
            "txn_type": str(row.get("txn_type", "transfer")) if pd.notna(row.get("txn_type", None)) else "transfer",
            "status": "normal",
            "is_fraud": 0,
            "fraud_score": 0.0,
        })
        next_num += 1
        inserted += 1

    if new_rows:
        db.bulk_insert_mappings(Transaction, new_rows)
        db.commit()

    return UploadResult(inserted=inserted, skipped=skipped, errors=errors)

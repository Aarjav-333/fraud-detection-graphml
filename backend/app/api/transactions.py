import io
from typing import Optional
from datetime import datetime
import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, UploadFile, File
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models.transaction import Transaction
from app.models.account import Account
from app.schemas.transaction import (
    TransactionCreate, TransactionUpdate, TransactionOut, TransactionList, UploadResult,
)
from app.crud import transaction as crud
from app.services.notifications import CHUNK, confirmed_fraud_senders, on_transactions_recorded

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


def _replay(existing: Transaction, data: TransactionCreate, response: Response) -> Transaction:
    """The transaction an Idempotency-Key already recorded - only if this request
    asks for the same transaction; a key reused for different details is an error."""
    same = (existing.sender_uid == data.sender_uid and existing.receiver_uid == data.receiver_uid
            and existing.amount == data.amount and existing.txn_type == (data.txn_type or "transfer")
            and (data.timestamp is None or existing.timestamp == data.timestamp.replace(tzinfo=None)))
    if not same:
        raise HTTPException(status_code=422, detail=(
            f"This Idempotency-Key was already used for transaction {existing.txn_uid} with different "
            "details. Use a new key for a different transaction."))
    response.status_code = 200
    return existing


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(
    data: TransactionCreate,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", min_length=1, max_length=200),
    db: Session = Depends(get_db),
):
    """Record a transaction. With an Idempotency-Key header, a retry of the same
    submission returns the transaction already recorded (200) instead of a
    second one; the same key with different details is rejected (422).
    Transactions by accounts confirmed as fraud notify analysts."""
    if idempotency_key:
        existing = crud.get_by_idempotency_key(db, idempotency_key)
        if existing:
            return _replay(existing, data, response)
    # follow the workflow rule: reject transactions referencing unknown accounts
    if not crud.account_exists(db, data.sender_uid):
        raise HTTPException(status_code=400, detail=f"Sender account '{data.sender_uid}' does not exist")
    if not crud.account_exists(db, data.receiver_uid):
        raise HTTPException(status_code=400, detail=f"Receiver account '{data.receiver_uid}' does not exist")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
    try:
        txn = crud.create_transaction(db, data, idempotency_key=idempotency_key)
    except IntegrityError:
        db.rollback()
        existing = crud.get_by_idempotency_key(db, idempotency_key) if idempotency_key else None
        if existing is None:
            raise HTTPException(status_code=409, detail="Could not record the transaction; please retry.")
        return _replay(existing, data, response)   # recorded by a concurrent retry
    on_transactions_recorded(db, [txn])
    return txn


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
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bulk-upload transactions from a CSV.

    Required columns: sender_uid, receiver_uid, amount.
    Optional columns: timestamp, txn_type, idempotency_key.
    Rows referencing unknown accounts or with invalid amounts are skipped and reported,
    and so are rows whose idempotency_key was already recorded (uploading the same
    file twice then adds nothing the second time).
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    raw = file.file.read()
    try:
        # keys as text: pandas would otherwise turn 1001 into 1001.0 when the column has a blank
        df = pd.read_csv(io.BytesIO(raw), dtype={"idempotency_key": str})
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
    keys, known_keys = set(), set()   # keys in this file so far; keys recorded before
    if "idempotency_key" in df.columns:
        given = sorted({str(k).strip() for k in df["idempotency_key"].dropna()} - {""})
        for i in range(0, len(given), CHUNK):
            known_keys |= {k for (k,) in db.query(Transaction.idempotency_key)
                           .filter(Transaction.idempotency_key.in_(given[i:i + CHUNK]))}

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
        key = row.get("idempotency_key")
        key = str(key).strip() if key is not None and pd.notna(key) and str(key).strip() else None
        if key and (key in known_keys or key in keys):
            skipped += 1
            if len(errors) < 20:
                errors.append(f"Row {line}: idempotency_key '{key}' was already recorded")
            continue
        if key:
            keys.add(key)

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
            "idempotency_key": key,
        })
        next_num += 1
        inserted += 1

    if new_rows:
        db.bulk_insert_mappings(Transaction, new_rows)
        db.commit()
        # only transactions sent by confirmed-fraud accounts can raise a notification
        flagged = confirmed_fraud_senders(db, {r["sender_uid"] for r in new_rows})
        uids = [r["txn_uid"] for r in new_rows if r["sender_uid"] in flagged]
        if uids:
            recorded = [t for i in range(0, len(uids), CHUNK)
                        for t in db.query(Transaction).filter(Transaction.txn_uid.in_(uids[i:i + CHUNK]))]
            on_transactions_recorded(db, recorded)

    return UploadResult(inserted=inserted, skipped=skipped, errors=errors)

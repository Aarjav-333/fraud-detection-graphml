"""Fraud notifications for analysts: history, read state, and a live stream.

The stream is a WebSocket. Browsers can't put a token in a WebSocket's
headers, so the client sends it as the first message (never in the URL,
where it would end up in logs):
    -> {"type": "auth", "token": "<JWT>", "after_id": <newest id it has>}
    <- {"type": "ready", "unread": n}
    <- {"type": "notification", "notification": {...}, "unread": n}   (as they happen)
    <- {"type": "unread", "unread": n}           (read state changed elsewhere)
Close codes: 4401 not authenticated / token expired, 4403 not a fraud analyst.
A client that reconnects with the newest id it has gets anything it missed.
"""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.deps import is_fraud_analyst, require_fraud_analyst, user_for_token
from app.models.user import User
from app.services import notifications as svc

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

AUTH_TIMEOUT = 10        # seconds a new connection has to authenticate
RECHECK_SECONDS = 15     # also re-read the database this often (missed wake-ups, other processes)
BATCH = 50


@router.get("")
def list_notifications(skip: int = 0, limit: int = Query(25, le=200), unread_only: bool = False,
                       db: Session = Depends(get_db), user: User = Depends(require_fraud_analyst)):
    total, items = svc.list_for_user(db, user.id, skip=skip, limit=limit, unread_only=unread_only)
    return {"total": total, "unread": svc.unread_count(db, user.id), "items": items}


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(require_fraud_analyst)):
    return {"unread": svc.unread_count(db, user.id)}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(require_fraud_analyst)):
    marked = svc.mark_all_read(db, user.id)
    return {"marked": marked, "unread": svc.unread_count(db, user.id)}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_fraud_analyst)):
    if not svc.set_read(db, notification_id, user.id, True):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"id": notification_id, "read": True, "unread": svc.unread_count(db, user.id)}


@router.post("/{notification_id}/unread")
def mark_unread(notification_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_fraud_analyst)):
    if not svc.set_read(db, notification_id, user.id, False):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"id": notification_id, "read": False, "unread": svc.unread_count(db, user.id)}


# ------------------------------------------------------------------ live stream

def _authenticate(token: str):
    db = SessionLocal()
    try:
        user, expires = user_for_token(db, token)
        if user is None:
            return None, None, None
        return user.id, is_fraud_analyst(user), expires
    finally:
        db.close()


def _changes(user_id: int, after_id: int):
    db = SessionLocal()
    try:
        _, items = svc.list_for_user(db, user_id, limit=BATCH, after_id=after_id)
        return items, svc.unread_count(db, user_id)
    finally:
        db.close()


def _start_id(after_id) -> int:
    if isinstance(after_id, int) and after_id >= 0:
        return after_id
    db = SessionLocal()
    try:
        return svc.latest_id(db)   # a client with no history: only new notifications from now
    finally:
        db.close()


async def _drain(ws: WebSocket) -> None:
    """Read (and ignore) what the client sends, so a disconnect is noticed at once."""
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        return


@router.websocket("/ws")
async def stream(ws: WebSocket):
    await ws.accept()
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, RuntimeError):
        await _close(ws, 4401, "Authenticate first")
        return
    user_id, analyst, expires = await run_in_threadpool(
        _authenticate, hello.get("token") if isinstance(hello, dict) else None)
    if user_id is None:
        await _close(ws, 4401, "Not authenticated")
        return
    if not analyst:
        await _close(ws, 4403, "This needs a fraud analyst account")
        return

    last_id = await run_in_threadpool(_start_id, hello.get("after_id"))
    wake = svc.broker.subscribe()
    reader = asyncio.create_task(_drain(ws))
    unread = None
    try:
        while not reader.done():
            if expires is not None and time.time() >= expires:
                await _close(ws, 4401, "Token expired")
                return
            wake.clear()   # before reading, so a change during the read wakes us again
            while True:
                items, count = await run_in_threadpool(_changes, user_id, last_id)
                for item in items:
                    await ws.send_json({"type": "notification", "notification": item, "unread": count})
                    last_id = item["id"]
                if len(items) < BATCH:
                    break
            if unread is None:
                await ws.send_json({"type": "ready", "unread": count})
            elif count != unread and not items:
                await ws.send_json({"type": "unread", "unread": count})
            unread = count
            woken = asyncio.create_task(wake.wait())
            timeout = RECHECK_SECONDS if expires is None else max(0.1, min(RECHECK_SECONDS, expires - time.time()))
            await asyncio.wait({reader, woken}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            woken.cancel()
    except (WebSocketDisconnect, RuntimeError, ConnectionError):
        pass   # the client went away; nothing to clean up beyond the finally
    finally:
        svc.broker.unsubscribe(wake)
        reader.cancel()


async def _close(ws: WebSocket, code: int, reason: str) -> None:
    try:
        await ws.close(code=code, reason=reason)
    except (RuntimeError, WebSocketDisconnect):
        pass

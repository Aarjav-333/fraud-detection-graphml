from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exc
    return user


# Roles allowed to review and confirm fraud, receive fraud notifications and
# see model analytics. Other roles (e.g. "viewer") can still use the rest of the app.
FRAUD_ANALYST_ROLES = ("admin", "analyst")


def is_fraud_analyst(user: User) -> bool:
    return (user.role or "").strip().lower() in FRAUD_ANALYST_ROLES


def require_fraud_analyst(user: User = Depends(get_current_user)) -> User:
    if not is_fraud_analyst(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This needs a fraud analyst account.")
    return user


def user_for_token(db: Session, token: str) -> tuple[User | None, float | None]:
    """The user a token belongs to and when it expires (a Unix time), or
    (None, None) if it is invalid or expired. For connections that can't send
    the Authorization header, like WebSockets."""
    try:
        payload = jwt.decode(token or "", settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None, None
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first() if username else None
    return (user, payload.get("exp")) if user else (None, None)

"""Create all tables and seed the admin user.

Run from the backend/ folder:
    python -m scripts.init_db
"""
from app.database import Base, engine, SessionLocal
from app.config import settings
from app.core.security import hash_password
from app import models  # noqa: F401  (registers all tables on Base.metadata)
from app.models.user import User


def init():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if existing:
            print(f"Admin '{settings.ADMIN_USERNAME}' already exists.")
        else:
            admin = User(
                username=settings.ADMIN_USERNAME,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
            )
            db.add(admin)
            db.commit()
            print(f"Created admin user '{settings.ADMIN_USERNAME}'.")
    finally:
        db.close()


if __name__ == "__main__":
    init()

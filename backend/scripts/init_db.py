"""Create all tables and seed the admin user.

Run from the backend/ folder:
    python -m scripts.init_db
"""
from app.database import engine, SessionLocal
from app.config import settings
from app.core.security import hash_password
from app.migrations import run_migrations
from app.models.user import User


def init():
    applied = run_migrations(engine)   # creates missing tables and columns; keeps existing data
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if existing:
            # Keep the admin password in sync with the current ADMIN_PASSWORD env var.
            # Without this, an admin created on an earlier boot (e.g. before the env
            # var was set) would keep its old password and cause 401 on login.
            existing.hashed_password = hash_password(settings.ADMIN_PASSWORD)
            existing.role = "admin"
            db.commit()
            print(f"Admin '{settings.ADMIN_USERNAME}' password synced to current ADMIN_PASSWORD.")
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

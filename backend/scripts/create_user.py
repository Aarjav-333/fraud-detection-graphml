"""Create a user, or update an existing one's role and password.

Roles: admin and analyst can review and confirm fraud, receive fraud
notifications and see model analytics; viewer can use the rest of the console.

Run from the backend/ folder:
    python -m scripts.create_user priya --role analyst
The password is asked for (twice) and never shown. For scripts, put it in the
NEW_USER_PASSWORD environment variable instead.
"""
import argparse
import getpass
import os

from app.core.security import hash_password
from app.database import SessionLocal, engine
from app.migrations import run_migrations
from app.models.user import User

ROLES = ("admin", "analyst", "viewer")
MIN_PASSWORD_LENGTH = 12


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    parser.add_argument("--role", choices=ROLES, default="analyst")
    args = parser.parse_args()

    password = os.environ.get("NEW_USER_PASSWORD")
    if password is None:
        password = getpass.getpass(f"Password for {args.username}: ")
        if password != getpass.getpass("Repeat it: "):
            raise SystemExit("The passwords don't match.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Use a password of at least {MIN_PASSWORD_LENGTH} characters.")

    run_migrations(engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            db.add(User(username=args.username, hashed_password=hash_password(password), role=args.role))
            print(f"Created {args.role} '{args.username}'.")
        else:
            user.hashed_password, user.role = hash_password(password), args.role
            print(f"Updated '{args.username}': role {args.role}, new password.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()

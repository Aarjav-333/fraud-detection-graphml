#!/usr/bin/env bash
# Render start command: seed the DB on first boot (or after a data reset), then serve.
set -e
cd "$(dirname "$0")/.."

python -m scripts.init_db

ACCOUNT_COUNT=$(python -c "
from app.database import SessionLocal
from app.models.account import Account
db = SessionLocal()
print(db.query(Account).count())
db.close()
")

if [ "$ACCOUNT_COUNT" -eq 0 ]; then
    echo "No account data found — seeding synthetic dataset..."
    python -m scripts.seed_data
else
    echo "Account data already present ($ACCOUNT_COUNT accounts) — skipping reseed."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

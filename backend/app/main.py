from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.migrations import run_migrations_safely
from app.api import (
    auth, accounts, transactions, preprocessing, rules, graph, features,
    ml, gnn, alerts, rings, cases, dashboard, reports, investigation, notifications, system, demo,
)

# Adds any table or column introduced since the database was first set up;
# existing data is left untouched (see app/migrations.py).
run_migrations_safely(engine)

app = FastAPI(title="Financial Fraud Detection with Graph ML")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(preprocessing.router)
app.include_router(rules.router)
app.include_router(graph.router)
app.include_router(features.router)
app.include_router(ml.router)
app.include_router(gnn.router)
app.include_router(alerts.router)
app.include_router(rings.router)
app.include_router(cases.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(investigation.router)
app.include_router(notifications.router)
app.include_router(system.router)
app.include_router(demo.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "fraud-detection-graphml"}

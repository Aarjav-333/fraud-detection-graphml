from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, accounts, transactions, preprocessing, rules, graph, features, ml, gnn, alerts, rings, cases, gnn, rules

app = FastAPI(title="Financial Fraud Detection with Graph ML")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
app.include_router(gnn.router)
app.include_router(alerts.router)
app.include_router(rings.router)
app.include_router(cases.router)
app.include_router(rules.router)
app.include_router(graph.router)
app.include_router(features.router)
app.include_router(ml.router)
app.include_router(gnn.router)
app.include_router(alerts.router)
app.include_router(rings.router)
app.include_router(cases.router)
app.include_router(gnn.router)
app.include_router(alerts.router)
app.include_router(rings.router)
app.include_router(cases.router)


@app.get("/")
def root():
    return {"status": "ok", "message": "Fraud Detection API running"}

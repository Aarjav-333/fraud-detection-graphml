"""ML risk scoring — baseline models (workflow Step 10, part A).

Trains on the account feature matrix (Phase 8):
  RandomForest       - supervised baseline, class_weight='balanced' for imbalance
  XGBoost            - supervised baseline, scale_pos_weight for imbalance
  IsolationForest    - unsupervised anomaly detection (never sees labels)

Evaluates on a held-out stratified test set (accuracy, precision, recall, F1, ROC-AUC),
then scores ALL accounts with the best supervised model and writes:
  Account.fraud_score  (probability of fraud, 0..1)
"""
import os
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from sqlalchemy.orm import Session

from app.ml.features import load_features
from app.models.account import Account

SAVED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_models")
RESULTS_JSON = os.path.join(SAVED_DIR, "baseline_results.json")

FEATURE_COLS = [
    "total_sent", "total_received", "txn_count_sent", "txn_count_received",
    "unique_receivers", "unique_senders", "avg_sent_amount", "avg_received_amount",
    "max_sent_amount", "max_received_amount", "txn_per_active_day",
    "in_degree", "out_degree", "degree_centrality", "pagerank", "in_cycle", "community_size",
]


def _metrics(y_true, y_pred, y_score=None) -> dict:
    out = {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
    }
    if y_score is not None:
        out["roc_auc"] = round(roc_auc_score(y_true, y_score), 4)
    return out


def train_and_score(db: Session, test_size: float = 0.25, seed: int = 42) -> dict:
    df = load_features()
    if df is None:
        raise ValueError("Features not built. Run feature engineering first.")

    X = df[FEATURE_COLS].values
    y = df["is_fraud"].values
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed,
    )
    n_pos, n_neg = int(y_train.sum()), int(len(y_train) - y_train.sum())

    results, models = {}, {}

    # --- Random Forest (class-weighted) ---
    rf = RandomForestClassifier(
        n_estimators=300, class_weight="balanced", random_state=seed, n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    rf_score = rf.predict_proba(X_test)[:, 1]
    results["random_forest"] = _metrics(y_test, (rf_score >= 0.5).astype(int), rf_score)
    models["random_forest"] = rf

    # --- XGBoost (scale_pos_weight) ---
    xgb = XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.1,
        scale_pos_weight=n_neg / max(n_pos, 1),
        eval_metric="logloss", random_state=seed, n_jobs=-1,
    )
    xgb.fit(X_train, y_train)
    xgb_score = xgb.predict_proba(X_test)[:, 1]
    results["xgboost"] = _metrics(y_test, (xgb_score >= 0.5).astype(int), xgb_score)
    models["xgboost"] = xgb

    # --- Isolation Forest (unsupervised; contamination = observed fraud rate) ---
    iso = IsolationForest(
        n_estimators=200, contamination=float(y.mean()), random_state=seed, n_jobs=-1,
    )
    iso.fit(X_train)
    iso_pred = (iso.predict(X_test) == -1).astype(int)
    iso_score = -iso.score_samples(X_test)  # higher = more anomalous
    results["isolation_forest"] = _metrics(y_test, iso_pred, iso_score)

    # --- feature importance (from the best supervised model by F1) ---
    best_name = max(("random_forest", "xgboost"), key=lambda k: results[k]["f1"])
    best = models[best_name]
    importances = best.feature_importances_
    top_features = sorted(
        zip(FEATURE_COLS, importances.tolist()), key=lambda t: t[1], reverse=True,
    )[:8]

    # --- score ALL accounts with the best model, write back ---
    all_scores = best.predict_proba(X)[:, 1]
    df_scores = pd.DataFrame({"account_uid": df["account_uid"], "score": all_scores})
    for i in range(0, len(df_scores), 500):
        chunk = df_scores.iloc[i:i + 500]
        mapping = dict(zip(chunk["account_uid"], chunk["score"]))
        accounts = db.query(Account).filter(Account.account_uid.in_(list(mapping))).all()
        for acc in accounts:
            acc.fraud_score = round(float(mapping[acc.account_uid]), 4)
    db.commit()

    os.makedirs(SAVED_DIR, exist_ok=True)
    joblib.dump(best, os.path.join(SAVED_DIR, f"{best_name}.joblib"))

    summary = {
        "train_size": int(len(y_train)), "test_size": int(len(y_test)),
        "class_balance": {"fraud_in_train": n_pos, "legit_in_train": n_neg},
        "results": results,
        "best_model": best_name,
        "top_features": [{"feature": f, "importance": round(v, 4)} for f, v in top_features],
        "accounts_scored": int(len(df_scores)),
    }
    with open(RESULTS_JSON, "w") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def load_results() -> dict | None:
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON) as fh:
            return json.load(fh)
    return None

"""Test case 1 (model performance analytics) and the missing-results part of 7.

GraphSAGE and GCN are trained on a small generated graph, then every metric
the analytics API reports is recomputed from the saved test predictions.
"""
import hashlib
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import (
    accuracy_score, average_precision_score, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score,
)

from app.config import settings
from app.ml import gnn
from app.models.transaction import Transaction


def test_no_results_yet(client, users, monkeypatch):
    monkeypatch.setattr(gnn, "load_results", lambda: None)
    res = client.get("/api/gnn/evaluation", params={"source": "elliptic"}, headers=users["analyst"])
    assert res.status_code == 200
    assert res.json() == {"source": "elliptic", "sources_with_results": [], "models": {}, "same_test_split": None}


def test_results_from_before_evaluations_were_recorded(client, users, monkeypatch):
    legacy = {"synthetic_gcn": {"source": "synthetic", "model": "gcn", "epochs": 500, "train_nodes": 3751,
                                "test_nodes": 1249, "metrics": {"accuracy": 0.72, "f1": 0.61},
                                "loss_curve": [{"epoch": 0, "loss": 0.7}]}}
    monkeypatch.setattr(gnn, "load_results", lambda: legacy)
    body = client.get("/api/gnn/evaluation", headers=users["analyst"]).json()
    gcn = body["models"]["gcn"]
    assert gcn["detailed"] is False and gcn["evaluation"] is None and gcn["history"] == []
    assert gcn["metrics"] == {"accuracy": 0.72, "f1": 0.61}          # only what was really recorded
    assert gcn["threshold"] is None and gcn["model_version"] is None
    assert body["same_test_split"] is None


def test_analytics_need_a_fraud_analyst(client, users):
    assert client.get("/api/gnn/evaluation", headers=users["viewer"]).status_code == 403
    assert client.get("/api/gnn/evaluation").status_code == 401


@pytest.fixture(scope="module")
def trained(client, users):
    pytest.importorskip("torch_geometric")
    from conftest import SessionLocal

    rng = np.random.default_rng(7)
    n = 600
    uids = [f"G{i:05d}" for i in range(n)]
    fraud = (rng.random(n) < 0.25).astype(int)
    features = pd.DataFrame({col: rng.normal(size=n) for col in gnn.FEATURE_COLS})
    features["max_sent_amount"] += 1.2 * fraud           # a real but noisy signal
    features["in_degree"] += 0.8 * fraud
    features.insert(0, "account_uid", uids)
    features["is_fraud"] = fraud
    os.makedirs(settings.processed_dir, exist_ok=True)
    features.to_csv(settings.features_csv, index=False)

    session = SessionLocal()
    rows = []
    for i in range(n):                                   # fraud accounts mostly pay each other
        pool = np.flatnonzero(fraud == fraud[i]) if rng.random() < 0.8 else np.arange(n)
        for j in rng.choice(pool, size=4, replace=False):
            if j != i:
                rows.append({"txn_uid": f"GT{len(rows):07d}", "sender_uid": uids[i], "receiver_uid": uids[j],
                             "amount": 100.0, "txn_type": "transfer", "status": "normal"})
    session.bulk_insert_mappings(Transaction, rows)
    session.commit()
    session.close()

    for model in ("graphsage", "gcn"):
        res = client.post("/api/gnn/train", json={"source": "synthetic", "model": model, "epochs": 40},
                          headers=users["analyst"])
        assert res.status_code == 200, res.text
    return features


def test_both_models_evaluated_on_the_same_test_split(client, users, trained):
    body = client.get("/api/gnn/evaluation", params={"source": "synthetic"}, headers=users["analyst"]).json()
    assert set(body["models"]) == {"graphsage", "gcn"} and body["same_test_split"] is True
    assert body["sources_with_results"] == ["synthetic"]
    saved = gnn.load_results()
    node_sets = []
    for model, m in body["models"].items():
        artifacts = saved[f"synthetic_{model}"]["artifacts"]
        predictions = np.load(settings.saved_model_file(artifacts["test_predictions"]))
        node_sets.append(predictions["node_index"].tolist())
        # labels are the dataset's, for exactly the test nodes
        assert predictions["y_true"].tolist() == trained["is_fraud"].to_numpy()[predictions["node_index"]].tolist()
        weights = Path(settings.saved_model_file(artifacts["weights"])).read_bytes()
        assert m["model_version"] == f"{model}-synthetic-{hashlib.sha256(weights).hexdigest()[:12]}"
        assert m["detailed"] is True and m["threshold"] == 0.5 and m["trained_at"] and m["evaluated_at"]
        assert m["dataset"]["name"] == "Synthetic account graph" and m["dataset"]["nodes"] == len(trained)
        assert m["train_nodes"] + m["val_nodes"] + m["test_nodes"] == len(trained)
    assert node_sets[0] == node_sets[1]


def test_reported_metrics_match_the_predictions(client, users, trained):
    body = client.get("/api/gnn/evaluation", params={"source": "synthetic"}, headers=users["analyst"]).json()
    saved = gnn.load_results()
    for model, m in body["models"].items():
        p = np.load(settings.saved_model_file(saved[f"synthetic_{model}"]["artifacts"]["test_predictions"]))
        y, prob = p["y_true"], p["y_prob"]
        pred = (prob >= m["threshold"]).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        expected = {
            "accuracy": accuracy_score(y, pred), "precision": precision_score(y, pred, zero_division=0),
            "recall": recall_score(y, pred, zero_division=0), "f1": f1_score(y, pred, zero_division=0),
            "roc_auc": roc_auc_score(y, prob), "pr_auc": average_precision_score(y, prob),
            "false_positive_rate": fp / (fp + tn), "false_negative_rate": fn / (fn + tp),
        }
        reported = m["evaluation"]["metrics"]
        for name, value in expected.items():
            assert reported[name] == pytest.approx(round(float(value), 4), abs=1e-4), (model, name)
        assert m["evaluation"]["confusion_matrix"] == {"tn": tn, "fp": fp, "fn": fn, "tp": tp}
        assert m["metrics"] == reported                     # the GNN page shows the same numbers
        assert m["evaluation"]["support"] == {"positives": int(y.sum()), "negatives": int(len(y) - y.sum())}

        roc, pr = m["evaluation"]["roc_curve"], m["evaluation"]["pr_curve"]
        assert roc["fpr"][0] == 0 and roc["fpr"][-1] == 1 and roc["tpr"][-1] == 1
        assert roc["fpr"] == sorted(roc["fpr"]) and len(roc["fpr"]) <= gnn.CURVE_POINTS
        assert pr["recall"] == sorted(pr["recall"]) and len(pr["recall"]) == len(pr["precision"])

        history = m["history"]
        assert history[-1]["epoch"] == m["epochs"] and 10 <= len(history) <= gnn.HISTORY_POINTS + 1
        assert "loss_curve" not in saved[f"synthetic_{model}"]   # review fix 10: history has the training loss
        assert all({"train_loss", "val_loss", "train_accuracy", "val_accuracy"} <= set(h) for h in history)

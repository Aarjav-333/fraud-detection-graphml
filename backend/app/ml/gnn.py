"""Graph Neural Network risk scoring (workflow Step 10, part B).

Two data sources:
  synthetic : our own account graph (nodes=accounts, edges=transactions,
              features=Phase 8 matrix, labels=is_fraud). Fast, always available.
  elliptic  : the Elliptic Bitcoin dataset via PyTorch Geometric
              (auto-downloads ~500MB on first run; nodes=transactions,
              labels licit/illicit, temporal train/test split).

Two models: GCN and GraphSAGE. Class-imbalance handled with weighted cross-entropy.

Both models of a source use the same splits (fixed seed), so they are compared
on identical held-out test nodes. 15% of the training nodes are held back as a
validation set that is only used to record the training curves. After training,
each model is evaluated once on the test nodes - metrics, confusion matrix, ROC
and precision-recall curves - and the results, weights and test predictions are
saved, so the Model Analytics page reads them without retraining.

Heavy deps (torch, torch_geometric) are imported inside functions so the rest of
the app works even when they are not installed. Install them with:
    pip install -r requirements-gnn.txt
"""
import hashlib
import io
import os
import time
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.ml.features import load_features
from app.ml.outputs import load_json, output_path, replacing, save_json
from app.models.transaction import Transaction

RESULTS_FILE = "gnn_results.json"
SOURCES = ("synthetic", "elliptic")
MODELS = ("graphsage", "gcn")
DECISION_THRESHOLD = 0.5    # a node is predicted fraud when its fraud probability is at least this
VAL_FRACTION = 0.15         # of the training nodes, held back to record validation curves
CURVE_POINTS = 200          # ROC / PR curves are stored with at most this many points
HISTORY_POINTS = 50         # training curves are recorded at most this many times (each costs a forward pass)
ELLIPTIC_ROOT = os.path.join(BACKEND_DIR, "data", "elliptic")   # a shared download cache, not an output

FEATURE_COLS = [
    "total_sent", "total_received", "txn_count_sent", "txn_count_received",
    "unique_receivers", "unique_senders", "avg_sent_amount", "avg_received_amount",
    "max_sent_amount", "max_received_amount", "txn_per_active_day",
    "in_degree", "out_degree", "degree_centrality", "pagerank", "in_cycle", "community_size",
]


class GNNDepsMissing(RuntimeError):
    pass


def _require_torch():
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
    except Exception as exc:
        raise GNNDepsMissing(
            "GNN dependencies are not installed. From the backend folder run: "
            "pip install -r requirements-gnn.txt"
        ) from exc


# ---------------------------------------------------------------- data prep
def prep_synthetic(db: Session) -> dict:
    """Torch-free data assembly for the synthetic account graph."""
    df = load_features()
    if df is None:
        raise ValueError("Features not built. Run feature engineering first.")

    uid_to_idx = {uid: i for i, uid in enumerate(df["account_uid"])}
    X = df[FEATURE_COLS].to_numpy(dtype=np.float32)
    # standardize features (GNNs are sensitive to scale)
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1.0
    X = (X - mean) / std
    y = df["is_fraud"].to_numpy(dtype=np.int64)

    pairs = set()
    for s, r in db.query(Transaction.sender_uid, Transaction.receiver_uid).all():
        si, ri = uid_to_idx.get(s), uid_to_idx.get(r)
        if si is None or ri is None or si == ri:
            continue
        pairs.add((si, ri))
        pairs.add((ri, si))  # undirected message passing
    edge_index = np.array(list(pairs), dtype=np.int64).T if pairs else np.zeros((2, 0), dtype=np.int64)

    return {
        "x": X, "y": y, "edge_index": edge_index,
        "num_nodes": len(df), "num_edges": edge_index.shape[1] // 2,
        "account_uids": df["account_uid"].tolist(),
    }


def _validation_split(train_idx: np.ndarray, y: np.ndarray, seed: int):
    """Hold back VAL_FRACTION of the training nodes, stratified by label."""
    rng = np.random.default_rng(seed + 1)
    val = []
    for label in (0, 1):
        nodes = train_idx[y[train_idx] == label]
        val.append(rng.permutation(nodes)[: int(round(len(nodes) * VAL_FRACTION))])
    val_idx = np.sort(np.concatenate(val))
    return np.setdiff1d(train_idx, val_idx), val_idx


def _split_id(test_idx: np.ndarray) -> str:
    """A fingerprint of the test nodes: equal ids mean two models were tested on the same nodes."""
    return hashlib.sha256(np.sort(np.asarray(test_idx, dtype=np.int64)).tobytes()).hexdigest()[:16]


def _synthetic_masks(y: np.ndarray, test_size: float = 0.25, seed: int = 42):
    rng = np.random.default_rng(seed)
    idx = np.arange(len(y))
    test_idx = []
    for label in (0, 1):
        li = idx[y == label]
        li = rng.permutation(li)
        test_idx.append(li[: int(len(li) * test_size)])
    test_idx = np.concatenate(test_idx)
    test_mask = np.zeros(len(y), dtype=bool)
    test_mask[test_idx] = True
    return ~test_mask, test_mask


# ---------------------------------------------------------------- models
def _build_model(model_type: str, in_dim: int, hidden: int = 64, out_dim: int = 2):
    import torch
    from torch_geometric.nn import GCNConv, SAGEConv

    conv_cls = {"gcn": GCNConv, "graphsage": SAGEConv}[model_type]

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = conv_cls(in_dim, hidden)
            self.conv2 = conv_cls(hidden, out_dim)
            self.dropout = torch.nn.Dropout(0.3)

        def forward(self, x, edge_index):
            x = self.conv1(x, edge_index).relu()
            x = self.dropout(x)
            return self.conv2(x, edge_index)

    return Net()


def _thin(*arrays, points: int = CURVE_POINTS) -> list[list[float]]:
    """At most `points` evenly spaced entries (first and last kept) of equally long arrays."""
    n = len(arrays[0])
    keep = np.unique(np.linspace(0, n - 1, min(n, points)).round().astype(int)) if n else []
    return [[round(float(a[i]), 4) for i in keep] for a in arrays]


def evaluate(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = DECISION_THRESHOLD) -> dict:
    """Test-set evaluation from the true labels and predicted fraud probabilities."""
    from sklearn.metrics import (
        accuracy_score, average_precision_score, confusion_matrix, f1_score, precision_recall_curve,
        precision_score, recall_score, roc_auc_score, roc_curve,
    )
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = (int(v) for v in confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel())
    both_classes = len(np.unique(y_true)) == 2
    metrics = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4) if both_classes else None,
        "pr_auc": round(float(average_precision_score(y_true, y_prob)), 4) if both_classes else None,
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else None,
        "false_negative_rate": round(fn / (fn + tp), 4) if fn + tp else None,
    }
    roc, pr = {}, {}
    if both_classes:
        fpr, tpr, _ = roc_curve(y_true, y_prob)
        fpr, tpr = _thin(fpr, tpr)
        roc = {"fpr": fpr, "tpr": tpr}
        precision, recall, _ = precision_recall_curve(y_true, y_prob)
        recall, precision = _thin(recall[::-1], precision[::-1])   # recall ascending, for plotting
        pr = {"recall": recall, "precision": precision}
    return {
        "threshold": threshold,
        "metrics": metrics,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "support": {"positives": int(y_true.sum()), "negatives": int(len(y_true) - y_true.sum())},
        "roc_curve": roc,
        "pr_curve": pr,
    }


# ---------------------------------------------------------------- training
def train(db: Session, source: str = "synthetic", model_type: str = "graphsage",
          epochs: int = 100, hidden: int = 64, lr: float = 0.01, seed: int = 42) -> dict:
    if source not in ("synthetic", "elliptic"):
        raise ValueError("source must be 'synthetic' or 'elliptic'")
    if model_type not in ("gcn", "graphsage"):
        raise ValueError("model must be 'gcn' or 'graphsage'")
    _require_torch()

    import torch
    from torch_geometric.data import Data

    torch.manual_seed(seed)
    t0 = time.time()
    started_at = datetime.utcnow()

    if source == "synthetic":
        prep = prep_synthetic(db)
        data = Data(
            x=torch.tensor(prep["x"]),
            y=torch.tensor(prep["y"]),
            edge_index=torch.tensor(prep["edge_index"]),
        )
        train_np, test_np = _synthetic_masks(prep["y"], seed=seed)
        train_mask = torch.tensor(train_np)
        test_mask = torch.tensor(test_np)
        dataset_info = {"name": "Synthetic account graph", "nodes": prep["num_nodes"],
                        "edges": prep["num_edges"], "features": len(FEATURE_COLS),
                        "split": "stratified random 75/25"}
    else:
        from torch_geometric.datasets import EllipticBitcoinDataset
        os.makedirs(ELLIPTIC_ROOT, exist_ok=True)
        dataset = EllipticBitcoinDataset(root=ELLIPTIC_ROOT)  # auto-downloads on first run
        data = dataset[0]
        known = data.y != 2  # exclude unknown-label nodes defensively
        train_mask = data.train_mask & known
        test_mask = data.test_mask & known
        dataset_info = {"name": "Elliptic Bitcoin dataset", "nodes": int(data.num_nodes),
                        "edges": int(data.num_edges), "features": int(data.num_features),
                        "split": "temporal (early time steps train, later test)"}

    # the same seeded split for every model of this source
    labels = data.y.numpy()
    train_idx, val_idx = _validation_split(np.flatnonzero(train_mask.numpy()), labels, seed)
    test_idx = np.flatnonzero(test_mask.numpy())
    train_mask = torch.zeros(data.num_nodes, dtype=torch.bool)
    train_mask[torch.tensor(train_idx)] = True
    val_mask = torch.zeros(data.num_nodes, dtype=torch.bool)
    val_mask[torch.tensor(val_idx)] = True

    # class-imbalance handling: weighted cross-entropy
    y_train = data.y[train_mask]
    counts = torch.bincount(y_train, minlength=2).float()
    weights = counts.sum() / (2 * counts.clamp(min=1))

    model = _build_model(model_type, data.num_features, hidden=hidden)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)

    history = []
    record_every = max(1, epochs // HISTORY_POINTS)
    y_all = data.y
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        loss = loss_fn(out[train_mask], y_all[train_mask])
        loss.backward()
        optimizer.step()
        if epoch % record_every == 0 or epoch == epochs - 1:
            model.eval()
            with torch.no_grad():
                logits = model(data.x, data.edge_index)
                pred = logits.argmax(dim=1)
                history.append({
                    "epoch": epoch + 1,
                    "train_loss": round(float(loss.item()), 4),
                    "val_loss": round(float(loss_fn(logits[val_mask], y_all[val_mask]).item()), 4),
                    "train_accuracy": round(float((pred[train_mask] == y_all[train_mask]).float().mean()), 4),
                    "val_accuracy": round(float((pred[val_mask] == y_all[val_mask]).float().mean()), 4),
                })

    model.eval()
    with torch.no_grad():
        prob = torch.softmax(model(data.x, data.edge_index), dim=1)[:, 1]
    y_true = y_all[test_mask].numpy()
    y_prob = prob[test_mask].numpy()
    evaluation = evaluate(y_true, y_prob)

    # Keep what was evaluated: the weights (their hash is the model version) and
    # the test predictions, from which every reported metric can be recomputed.
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    model_bytes = buffer.getvalue()
    weights_file = f"gnn_{source}_{model_type}.pt"
    predictions_file = f"gnn_{source}_{model_type}_test_predictions.npz"
    with replacing(output_path(weights_file)) as tmp, open(tmp, "wb") as fh:
        fh.write(model_bytes)
    with replacing(output_path(predictions_file)) as tmp, open(tmp, "wb") as fh:
        np.savez_compressed(fh, node_index=test_idx, y_true=y_true, y_prob=y_prob)

    summary = {
        "source": source, "model": model_type, "epochs": epochs, "hidden": hidden, "lr": lr, "seed": seed,
        "dataset": dataset_info,
        "train_nodes": int(train_mask.sum()), "val_nodes": int(val_mask.sum()), "test_nodes": int(test_mask.sum()),
        "split": {"test_split_id": _split_id(test_idx), "validation_fraction": VAL_FRACTION},
        "class_weights": [round(float(w), 3) for w in weights],
        "history": history,
        "metrics": evaluation["metrics"],
        "evaluation": evaluation,
        "threshold": DECISION_THRESHOLD,
        "model_version": f"{model_type}-{source}-{hashlib.sha256(model_bytes).hexdigest()[:12]}",
        "trained_at": started_at.isoformat(timespec="seconds") + "Z",
        "evaluated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "artifacts": {"weights": weights_file, "test_predictions": predictions_file},
        "train_seconds": round(time.time() - t0, 1),
    }

    all_results = load_results() or {}
    all_results[f"{source}_{model_type}"] = summary
    save_json(RESULTS_FILE, all_results, indent=2)
    return summary


def load_results() -> dict | None:
    return load_json(RESULTS_FILE)


def evaluation_report(source: str) -> dict:
    """GraphSAGE vs GCN on one source, from the saved results (no training).
    Results saved before evaluations were recorded have their summary metrics
    only; everything they lack is reported as missing, never filled in."""
    results = load_results() or {}
    models = {}
    for model_type in MODELS:
        r = results.get(f"{source}_{model_type}")
        if not r:
            continue
        evaluation = r.get("evaluation")
        models[model_type] = {
            "model": model_type,
            "model_version": r.get("model_version"),
            "trained_at": r.get("trained_at"),
            "evaluated_at": r.get("evaluated_at"),
            "threshold": r.get("threshold"),
            "epochs": r.get("epochs"),
            "train_seconds": r.get("train_seconds"),
            "dataset": r.get("dataset"),
            "train_nodes": r.get("train_nodes"),
            "val_nodes": r.get("val_nodes"),
            "test_nodes": r.get("test_nodes"),
            "test_split_id": (r.get("split") or {}).get("test_split_id"),
            "metrics": r.get("metrics") or {},
            "detailed": evaluation is not None,
            "evaluation": evaluation,
            "history": r.get("history") or [],
        }
    split_ids = {m["test_split_id"] for m in models.values()}
    same_split = None if len(models) < 2 or None in split_ids else len(split_ids) == 1   # None: can't tell
    return {
        "source": source,
        "sources_with_results": [s for s in SOURCES if any(f"{s}_{m}" in results for m in MODELS)],
        "models": models,
        "same_test_split": same_split,
    }

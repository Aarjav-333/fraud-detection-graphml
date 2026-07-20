"""Graph Neural Network risk scoring (workflow Step 10, part B).

Two data sources:
  synthetic : our own account graph (nodes=accounts, edges=transactions,
              features=Phase 8 matrix, labels=is_fraud). Fast, always available.
  elliptic  : the Elliptic Bitcoin dataset via PyTorch Geometric
              (auto-downloads ~500MB on first run; nodes=transactions,
              labels licit/illicit, temporal train/test split).

Two models: GCN and GraphSAGE. Class-imbalance handled with weighted cross-entropy.

Heavy deps (torch, torch_geometric) are imported inside functions so the rest of
the app works even when they are not installed. Install them with:
    pip install -r requirements-gnn.txt
"""
import os
import json
import time

import numpy as np
from sqlalchemy.orm import Session

from app.ml.features import load_features, FEATURES_CSV
from app.models.transaction import Transaction

SAVED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_models")
RESULTS_JSON = os.path.join(SAVED_DIR, "gnn_results.json")
ELLIPTIC_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "elliptic",
)

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


def _metrics(y_true, y_pred, y_score) -> dict:
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    )
    out = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    }
    try:
        out["roc_auc"] = round(float(roc_auc_score(y_true, y_score)), 4)
    except ValueError:
        out["roc_auc"] = None
    return out


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

    if source == "synthetic":
        prep = prep_synthetic(db)
        data = Data(
            x=torch.tensor(prep["x"]),
            y=torch.tensor(prep["y"]),
            edge_index=torch.tensor(prep["edge_index"]),
        )
        train_np, test_np = _synthetic_masks(prep["y"])
        train_mask = torch.tensor(train_np)
        test_mask = torch.tensor(test_np)
        dataset_info = {"nodes": prep["num_nodes"], "edges": prep["num_edges"],
                        "features": len(FEATURE_COLS), "split": "stratified random 75/25"}
    else:
        from torch_geometric.datasets import EllipticBitcoinDataset
        os.makedirs(ELLIPTIC_ROOT, exist_ok=True)
        dataset = EllipticBitcoinDataset(root=ELLIPTIC_ROOT)  # auto-downloads on first run
        data = dataset[0]
        known = data.y != 2  # exclude unknown-label nodes defensively
        train_mask = data.train_mask & known
        test_mask = data.test_mask & known
        dataset_info = {"nodes": int(data.num_nodes), "edges": int(data.num_edges),
                        "features": int(data.num_features),
                        "split": "temporal (early time steps train, later test)"}

    # class-imbalance handling: weighted cross-entropy
    y_train = data.y[train_mask]
    counts = torch.bincount(y_train, minlength=2).float()
    weights = counts.sum() / (2 * counts.clamp(min=1))

    model = _build_model(model_type, data.num_features, hidden=hidden)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)

    model.train()
    losses = []
    for epoch in range(epochs):
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        loss = loss_fn(out[train_mask], data.y[train_mask])
        loss.backward()
        optimizer.step()
        if epoch % max(1, epochs // 10) == 0 or epoch == epochs - 1:
            losses.append({"epoch": epoch, "loss": round(float(loss.item()), 4)})

    model.eval()
    with torch.no_grad():
        logits = model(data.x, data.edge_index)
        prob = torch.softmax(logits, dim=1)[:, 1]
        pred = logits.argmax(dim=1)

    y_true = data.y[test_mask].numpy()
    result = _metrics(y_true, pred[test_mask].numpy(), prob[test_mask].numpy())

    summary = {
        "source": source, "model": model_type, "epochs": epochs, "hidden": hidden,
        "dataset": dataset_info,
        "train_nodes": int(train_mask.sum()), "test_nodes": int(test_mask.sum()),
        "class_weights": [round(float(w), 3) for w in weights],
        "loss_curve": losses,
        "metrics": result,
        "train_seconds": round(time.time() - t0, 1),
    }

    os.makedirs(SAVED_DIR, exist_ok=True)
    all_results = load_results() or {}
    all_results[f"{source}_{model_type}"] = summary
    with open(RESULTS_JSON, "w") as fh:
        json.dump(all_results, fh, indent=2)
    return summary


def load_results() -> dict | None:
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON) as fh:
            return json.load(fh)
    return None

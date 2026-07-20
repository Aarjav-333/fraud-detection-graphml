# Financial Fraud Detection with Graph ML

A graph-based financial fraud detection & investigation system.
- **Backend:** FastAPI + SQLAlchemy (SQLite)
- **Frontend:** React (Vite) + Material UI
- **App data:** synthetic accounts/transactions (added Phase 3)
- **GNN benchmark:** Elliptic Bitcoin dataset (added Phase 9)

## Build progress
- [x] Phase 1: Backend foundation (DB models, admin login)
- [x] Phase 2: React frontend foundation (login, layout, protected routes)
- [x] Phase 3: Synthetic data generator (~5k accounts, 80k txns, planted fraud)
- [x] Phase 4: Account & Transaction CRUD + CSV upload
- [x] Phase 5: Data preprocessing (detect + auto-clean)
- [x] Phase 6: Rule-based fraud detection (6 rules, ~96% recall on planted fraud)
- [x] Phase 7: Graph construction + analysis (centrality, PageRank, communities, cycles)
- [x] Phase 8: Feature engineering (17 txn + graph features per account)
- [x] Phase 9A: ML scoring — RF / XGBoost / Isolation Forest (XGBoost F1 ≈ 0.83)
- [x] Phase 9B: GNN — GCN/GraphSAGE on synthetic graph + Elliptic benchmark
- [x] Phase 10: Fraud alerts (rule + ML sources, full status lifecycle)
- [x] Phase 11: Fraud ring detection + visualization (54 rings, ~97% purity)
- [ ] Phase 12: Investigation cases
- [x] Phase 13: Dashboard (stats, charts, top-risk view)
- [ ] Phase 14: Reports & export

## Generate & seed the synthetic dataset
Run these from the `backend/` folder (with the venv active):
```bash
# schema changed in Phase 3 (Account.is_fraud added) -> rebuild the DB once:
rm fraud_detection.db            # Windows: del fraud_detection.db
python -m scripts.init_db        # recreate tables + admin

python -m data.generate_synthetic   # writes data/raw/accounts.csv + transactions.csv
python -m scripts.seed_data         # loads the CSVs into the database
```
This creates ~5,000 accounts and ~80,000 transactions, ~3% of them fraudulent
(fraud rings, structuring, circular transfers, fan-out) with ground-truth labels.

> Note: Phase 4 added an `is_active` column to accounts. If you set up the DB before
> Phase 4, delete `fraud_detection.db` and re-run init_db + seed_data once more.

## GNN setup (Phase 9B)
The GNN needs PyTorch + PyTorch Geometric (kept separate because they are large):
```bash
cd backend
pip install -r requirements-gnn.txt   # ~200MB+ download, CPU-only is fine
```
Then restart the backend. On the GNN page:
- **Synthetic graph**: trains in seconds on your account network (needs Graph Analysis + Features built first).
- **Elliptic Bitcoin**: auto-downloads ~500MB into backend/data/elliptic on first run; training ~200k nodes takes several minutes on CPU.

## Run the backend
```bash
cd backend
python -m venv venv
# Windows:  venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then edit SECRET_KEY / admin password
python -m scripts.init_db       # creates tables + seeds admin
uvicorn app.main:app --reload   # runs on http://127.0.0.1:8000
```

## Run the frontend (in a second terminal)
```bash
cd frontend
npm install
cp .env.example .env            # VITE_API_URL points to the backend
npm run dev                     # runs on http://localhost:5173
```

Open http://localhost:5173, log in with **admin / admin123**.
Keep BOTH the backend and frontend running at the same time.

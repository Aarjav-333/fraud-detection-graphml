# Deployment Guide — Render (backend) + Vercel (frontend)

## Backend on Render (free tier)

1. Push this repo to GitHub (already done).
2. Go to https://dashboard.render.com -> New -> Web Service.
3. Connect your GitHub repo. Render will detect render.yaml -- click Apply.
   (No blueprint auto-detected? Configure manually:
     - Root directory: backend
     - Build command: pip install -r requirements.txt
     - Start command: bash scripts/render_start.sh
     - Plan: Free)
4. In the service's Environment tab, set:
     - ADMIN_PASSWORD = a real password (not the default)
     - SECRET_KEY = (Render auto-generates this via the blueprint)
     - ALLOWED_ORIGINS = leave as localhost for now -- update after step 6
5. Deploy. First boot seeds 5,000 accounts + 80,000 transactions automatically
   (takes ~15-20s). Note your backend URL, e.g. https://fraud-detection-backend.onrender.com
6. Free tier note: the service spins down after 15 min idle and cold-starts
   (~30-60s) on the next request -- normal for a demo, not for 24/7 uptime.
   Data also resets on redeploys/cold restarts; the start script reseeds
   automatically so the app is never left with an empty database.

## Frontend on Vercel

1. https://vercel.com/new -> import the same GitHub repo.
2. Set Root Directory to frontend.
3. Framework preset: Vite (auto-detected).
4. Add environment variable:
     - VITE_API_URL = your Render backend URL from above (no trailing slash)
5. Deploy. Note your Vercel URL, e.g. https://fraud-detection-graphml.vercel.app

## Connect them (CORS)

1. Back in Render -> your backend service -> Environment:
     - Set ALLOWED_ORIGINS = https://your-app.vercel.app (your real Vercel URL)
     - (Add ,http://localhost:5173 too if you still want local dev to work)
2. Render redeploys automatically when you save the env var.

## After deploy: run the pipeline

The database seeds with raw accounts/transactions automatically, but the
detection pipeline is a manual, explicit step (same as local) -- log in
(admin / your password) and click through in order:
Graph Analysis -> Features -> ML Scoring -> Rule Detection -> Fraud Alerts -> Fraud Rings

GNN training will show "dependencies not installed" -- requirements-gnn.txt
is intentionally not installed on Render's free tier (512MB RAM can't hold
torch + xgboost + sklearn together). Use your local GNN results for the report.

## Redeploying after code changes

Both Render and Vercel auto-deploy on git push origin main. No manual steps
needed beyond the one-time setup above.

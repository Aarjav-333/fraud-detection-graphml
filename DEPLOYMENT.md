# Deployment Guide — Render (backend) + Vercel (frontend)

## Already deployed? Check these before your next push

The backend now refuses to start unless APP_ENV=development (local only) or
its secrets are strong. An existing Render service that doesn't meet the rules
below will fail its next deploy (Render keeps the previous deploy running).
In Render -> your service -> Environment, make sure:
  - SECRET_KEY is set: 32+ characters, random, no surrounding spaces
    (generate one: python -c "import secrets; print(secrets.token_urlsafe(48))")
  - ADMIN_PASSWORD is set: 12+ characters, not containing admin123
  - APP_ENV is NOT set to development

## Backend on Render (free tier)

1. Push this repo to GitHub (already done).
2. Go to https://dashboard.render.com -> New -> Blueprint (not "Web Service" --
   only the Blueprint flow reads render.yaml).
3. Connect your GitHub repo. Render reads render.yaml and asks for the values
   marked sync: false:
     - ADMIN_PASSWORD = a real password, 12+ characters (not admin123)
     - ALLOWED_ORIGINS = http://localhost:5173 for now -- you change it in
       "Connect them" below, once the Vercel URL exists
   SECRET_KEY is generated for you. Click Apply.
4. Deploy. First boot seeds 5,000 accounts + 80,000 transactions automatically
   (takes ~15-20s). Note your backend URL, e.g. https://fraud-detection-backend.onrender.com

   Deploy failed with "Refusing to start with APP_ENV='production' and
   insecure settings"? That's on purpose: the message lists exactly which
   rule failed (SECRET_KEY missing, a placeholder, under 32 characters or too
   repetitive; ADMIN_PASSWORD missing, containing admin123 or under 12
   characters; or either one with surrounding spaces). Fix it in the service's
   Environment tab and redeploy. Secret values are never printed in the log.

   Prefer to skip the Blueprint? New -> Web Service works too, but then you
   must set every variable yourself:
     - Root directory: backend
     - Build command: pip install -r requirements.txt
     - Start command: bash scripts/render_start.sh
     - Plan: Free
     - Environment: SECRET_KEY = output of: python -c "import secrets; print(secrets.token_urlsafe(48))"
                    ADMIN_PASSWORD = a real password, 12+ characters
                    ALLOWED_ORIGINS = http://localhost:5173 (updated later)
     - Do NOT set APP_ENV -- leaving it unset is what turns the checks on.
5. Free tier note: the service spins down after 15 min idle and cold-starts
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
   (frontend/vercel.json rewrites page paths to index.html, so refreshing or
   bookmarking a page like /rules works instead of returning a 404. Missing
   files under /assets/ still return a real 404.)

## Connect them (CORS)

1. Back in Render -> your backend service -> Environment:
     - Set ALLOWED_ORIGINS = https://your-app.vercel.app (your real Vercel URL;
       pasting it straight from the address bar is fine -- any path, trailing
       slash or capital letters are normalized away)
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

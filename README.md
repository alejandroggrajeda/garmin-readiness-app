# garmin-app

A personal Garmin Connect companion that derives a "Training Readiness"
score from historical HRV, sleep, body battery and stress data, refreshed
by a manual "sync now" action (no scheduled/background sync). See
`design.md` (in project planning history) for the full architecture; the
short version:

- **`backend/`** — Python 3.12, FastAPI + SQLAlchemy + Alembic. Hexagonal:
  the `readiness/` scoring core is a pure, I/O-free module; Garmin,
  Postgres and the clock are edge adapters. Single user, one static API
  key. Deploys to Render's free tier against a Neon free Postgres
  instance (direct, non-pooled endpoint).
- **`mobile/`** — Expo (React Native + TypeScript). Thin, read-only client:
  today's score/band/reason (or an explicit calibrating/insufficient-data
  state), a manual sync control with in-flight/failure states, a
  last-synced-at indicator, and a 30-day trends view.

This repository was built phase-by-phase (SDD-driven, 7 stacked PRs) and is
now feature-complete end to end: Garmin sync, health metrics storage,
readiness scoring, the readiness/sync API, and the mobile dashboard.

## Backend

### Setup

```bash
cd backend
py -m venv .venv          # or: python -m venv .venv
./.venv/Scripts/pip install -e ".[dev]"    # Windows
# .venv/bin/pip install -e ".[dev]"        # macOS/Linux
cp .env.example .env       # then fill in real values for local use
```

### Run tests

```bash
cd backend
./.venv/Scripts/python -m pytest      # Windows
# .venv/bin/python -m pytest          # macOS/Linux
```

Tests that need a real Postgres (`tests/integration/`) use a
`testcontainers`-managed disposable Postgres container and require a local
Docker daemon; `tests/integration/test_healthz.py` is the one exception
that never touches the database. `tests/contract/` and any test exercising
Garmin only ever talk to `FakeGarminGateway` with recorded fixtures — no
test in this repo makes a live Garmin Connect call.

Required env vars for local dev — copy `backend/.env.example` to
`backend/.env` and fill in `DATABASE_URL`, `API_KEY`, `GARMIN_EMAIL`,
`GARMIN_PASSWORD`, `GARMIN_SECRET_KEY` (see the file itself for how to
generate `API_KEY`/`GARMIN_SECRET_KEY`).

### Run the API locally

```bash
cd backend
./.venv/Scripts/uvicorn app.main:app --reload
```

### Trigger a sync

With the API running and an `API_KEY` configured:

```bash
curl -X POST http://localhost:8000/api/sync -H "X-API-Key: <your API_KEY>"
# -> 202 {"run_id": "..."}  (poll GET /api/sync/runs/{run_id} for status)
# -> 409 if a sync is already running, 423 if Garmin auth is locked,
#    429 if the cooldown from a rate-limit hasn't elapsed yet
```

Manual sync is the *only* sync trigger in this app by design — there is no
scheduler or background job. See `GET /api/readiness/today`'s
`last_synced_at`/`data_stale` fields for transparency about how old the
shown data is.

## Mobile

### Setup

```bash
cd mobile
npm install
cp .env.example .env    # then set EXPO_PUBLIC_API_KEY to match backend's API_KEY,
                         # and EXPO_PUBLIC_API_BASE_URL to your running backend
```

The API key is supplied via Expo's built-in `EXPO_PUBLIC_*` env var
inlining (no secure-storage dependency needed for this single-user app —
see `mobile/src/api/client.ts`'s docstring for the full reasoning and
`mobile/.env.example` for the exact variables).

### Run tests

```bash
cd mobile
npx jest
```

### Run the app

```bash
cd mobile
npx expo start
```

Scan the QR code with Expo Go (Android) or the Camera app (iOS) to run it
on a real device.

## Deployment

- Backend: `render.yaml` (repo root) — Render free web service, native
  Python buildpack, no Dockerfile. Env vars are documented in
  `backend/.env.example` and set as Render secrets, never committed.
- Database: Neon free-tier Postgres, **direct** (non-pooled) connection
  string — required for `pg_try_advisory_lock` correctness.
- Mobile: not published to an app store; run via `npx expo start` (Expo Go
  or a local dev build) pointed at the deployed backend URL.

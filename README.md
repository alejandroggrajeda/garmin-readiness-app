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
  today's score, history trends, and the manual sync control.

This repository is under active, phased development (SDD-driven). Phase 1
delivers project scaffolding and the test harnesses only — no Garmin
integration, scoring engine, or real dashboard yet.

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

Tests that need a real Postgres (`tests/integration/`, from Phase 3
onward) use a `testcontainers`-managed disposable Postgres container and
require a local Docker daemon. The Phase 1 test suite (`tests/integration/
test_healthz.py`) does not touch the database.

### Run the API locally

```bash
cd backend
./.venv/Scripts/uvicorn app.main:app --reload
```

## Mobile

### Setup

```bash
cd mobile
npm install
```

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

## Deployment

- Backend: `render.yaml` (repo root) — Render free web service, native
  Python buildpack, no Dockerfile. Env vars are documented in
  `backend/.env.example` and set as Render secrets, never committed.
- Database: Neon free-tier Postgres, **direct** (non-pooled) connection
  string — required for `pg_try_advisory_lock` correctness.

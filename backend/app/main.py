from fastapi import FastAPI

from app.api.routes import health, readiness, sync

app = FastAPI(title="Garmin Readiness API")

app.include_router(health.router)
app.include_router(sync.router)
app.include_router(readiness.router)

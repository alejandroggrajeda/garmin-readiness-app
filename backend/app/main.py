from fastapi import FastAPI

from app.api.routes import health, sync

app = FastAPI(title="Garmin Readiness API")

app.include_router(health.router)
app.include_router(sync.router)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.models.db import init_db
from app.api.webhook import router as webhook_router
from app.api.dashboard import router as dashboard_router

app = FastAPI(title="Recurv AI — Autonomous Revenue Recovery for Razorpay")

init_db()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(webhook_router)
app.include_router(dashboard_router)


@app.get("/")
def health_check():
    return {"status": "ok", "app": "Recurv AI"}
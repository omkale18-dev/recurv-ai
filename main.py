from fastapi import FastAPI
from app.models.db import init_db
from app.api.webhook import router as webhook_router

app = FastAPI(title="Revenue Recovery Agent")

init_db()

app.include_router(webhook_router)


@app.get("/")
def health_check():
    return {"status": "ok"}
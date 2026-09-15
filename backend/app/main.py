from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import assistant, repo

app = FastAPI(title="CodeLiteracy API")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(repo.router)
app.include_router(assistant.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

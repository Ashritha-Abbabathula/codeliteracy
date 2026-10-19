from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import assistant, auth, chat, notebook, quiz, repo



@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # create tables / bring an older database up to the current models
    yield


app = FastAPI(title="CodeLiteracy API", version="2.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow development and production origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(repo.router)
app.include_router(assistant.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(notebook.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "2.1.0"}

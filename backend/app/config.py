from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str = ""
    github_token: str = ""
    database_url: str = "sqlite:///./data/codeliteracy.db"
    workspace_dir: str = "./workspace"
    frontend_origin: str = "http://localhost:5173"

    # Model used for every LLM call (explanations, assistant, quizzes, resources).
    # Gemini 2.5 Flash has a generous free tier (no billing required) and supports
    # both JSON-mode output and function calling, which is all CodeLiteracy needs.
    llm_model: str = "gemini-2.5-flash"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.workspace_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    return settings

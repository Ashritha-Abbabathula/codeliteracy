"""Test harness: an isolated temp database + workspace, and a scriptable fake LLM so tests are
deterministic and never spend Gemini quota. Env vars must be set before `app` is imported
(the engine and settings are created at import time)."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="codeliteracy-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["WORKSPACE_DIR"] = str(_TMP / "workspace")
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["GITHUB_TOKEN"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import llm_client  # noqa: E402
from app.services.llm_client import LLMCallError  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class FakeLLM:
    """Routes json_completion() by which system prompt is asking, and counts calls."""

    def __init__(self):
        self.calls: list[str] = []
        self.fail: str | None = None  # set to a message to make every call raise LLMCallError
        self.overrides: dict[str, object] = {}

    def __call__(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        kind = self._kind(system_prompt)
        self.calls.append(kind)
        if self.fail:
            raise LLMCallError(self.fail)
        if kind in self.overrides:
            value = self.overrides[kind]
            return value(user_prompt) if callable(value) else json.dumps(value)
        return json.dumps(self._default(kind, user_prompt))

    @staticmethod
    def _kind(system: str) -> str:
        if "onboarding tutor" in system:
            return "onboarding"
        if "documenting a codebase's architecture" in system:
            return "summaries"
        if "Code Explainer and Tutor" in system:
            return "file"
        if "explain exactly these lines" in system:
            return "lines"
        if "quiz engine" in system:
            return "quiz"
        if "Code Tutor" in system:
            return "chat"
        if "answered a quiz question wrong" in system:
            return "resource"
        if "explain what this one file does" in system.lower() or "Explain what this one file does" in system:
            return "single_file"
        return "other"

    @staticmethod
    def quiz(n: int, tag: str = "") -> list[dict]:
        return [
            {
                "concept": f"Concept {i}{tag}",
                "question": f"Question {i}{tag}?",
                "options": [f"right {i}{tag}", f"wrong-a {i}{tag}", f"wrong-b {i}{tag}", f"wrong-c {i}{tag}"],
                "correct_index": 0,
                "option_explanations": [f"yes {i}", f"no-a {i}", f"no-b {i}", f"no-c {i}"],
                "hint": f"hint {i}{tag}",
                "explanation": f"because {i}{tag}",
                "search_query": f"python topic {i}",
            }
            for i in range(n)
        ]

    def _default(self, kind: str, user_prompt: str):
        if kind == "onboarding":
            return {
                "greeting": "Hello!", "main_idea": "A demo project.",
                "tech_stack": [{"name": "FastAPI", "category": "Backend", "purpose": "API"}],
                "learning_curve": {"easy": ["easy thing"], "hard": ["hard thing"]},
                "folder_guide": [{"folder": "app", "title": "App", "purpose": "code", "key_files": ["main.py"]}],
                "learning_path": [
                    {"file_path": "app/models.py", "title": "Data first", "why": "Everything else uses Item."},
                    {"file_path": "services/store.py", "title": "Then storage", "why": "Wrong folder, right file name."},
                    {"file_path": "app/does_not_exist.py", "title": "Invented", "why": "Not a real file."},
                ],
                "transition_message": "Next: flowchart.",
            }
        if kind == "summaries":
            paths = [ln[4:].strip() for ln in user_prompt.splitlines() if ln.startswith("### ")]
            return {"summaries": {p: f"Role of {p}" for p in paths}}
        if kind == "file":
            return {
                "overview": "This file does things.",
                "key_concepts": [{"term": "router", "meaning": "Maps URLs to functions."}, {"term": "", "meaning": "dropped"}],
                "line_sections": [
                    {"start_line": 1, "end_line": 3, "title": "Setup", "explanation": "imports", "importance": "setup"},
                    {"start_line": 4, "end_line": 9999, "title": "Rest", "explanation": "logic", "importance": "core"},
                    {"start_line": 50, "end_line": 40, "title": "Bogus", "explanation": "inverted", "importance": "core"},
                ],
                "quizzes": self.quiz(4),
            }
        if kind == "lines":
            return {
                "summary": "These lines build an Item.",
                "notes": [
                    {"start_line": 4, "end_line": 4, "explanation": "Declares the class."},
                    {"start_line": 900, "end_line": 950, "explanation": "Outside the selection."},
                    {"start_line": 5, "end_line": 6, "explanation": "Stores the name."},
                ],
                "concepts": [{"term": "constructor", "meaning": "Runs when an object is created."}],
            }
        if kind == "quiz":
            return {"quizzes": self.quiz(3, " change")}
        if kind == "chat":
            return {"reply": "Here is why.", "suggested_followups": ["Why?", "Example?"]}
        if kind == "resource":
            return {"title": "Read this", "description": "It helps.", "search_query": "python topic"}
        if kind == "single_file":
            return {"explanation": "Does one thing."}
        return {}


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm_client, "json_completion", fake)
    return fake


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def sample_repo(tmp_path) -> Path:
    """A small layered Python project, committed to git."""
    root = tmp_path / "demo"
    (root / "app" / "routers").mkdir(parents=True)
    (root / "app" / "services").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "routers" / "__init__.py").write_text("")
    (root / "app" / "services" / "__init__.py").write_text("")
    (root / "app" / "main.py").write_text(
        '"""App entrypoint."""\nfrom fastapi import FastAPI\nfrom app.routers import items\n\napp = FastAPI()\napp.include_router(items.router)\n'
    )
    (root / "app" / "routers" / "items.py").write_text(
        '"""Item routes."""\nfrom fastapi import APIRouter\nfrom app.services.store import save_item\n\nrouter = APIRouter()\n\n\n@router.post("/items")\ndef create(name: str):\n    return save_item(name)\n'
    )
    (root / "app" / "services" / "store.py").write_text(
        '"""Stores items."""\nfrom app.models import Item\nimport sqlalchemy\n\n\ndef save_item(name):\n    return Item(name=name)\n'
    )
    (root / "app" / "models.py").write_text('"""Data models."""\n\n\nclass Item:\n    def __init__(self, name):\n        self.name = name\n')
    (root / "README.md").write_text("# Demo\n\nA tiny demo service that stores items for testing purposes.\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


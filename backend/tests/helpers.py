"""Small request helpers shared by tests (kept out of conftest.py, which pytest loads once)."""

from pathlib import Path

from fastapi.testclient import TestClient


def register(client: TestClient, name: str) -> dict:
    res = client.post("/api/auth/register", json={"username": name, "email": f"{name}@example.com", "password": "secret123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def connect(client: TestClient, path: Path, headers: dict | None = None) -> str:
    res = client.post("/api/repo/connect", json={"source": str(path)}, headers=headers or {})
    assert res.status_code == 200, res.text
    return res.json()["repo_id"]

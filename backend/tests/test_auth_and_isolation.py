from tests.helpers import connect, register


def test_register_login_me_logout(client):
    res = client.post("/api/auth/register", json={"username": "Alice", "email": "Alice@Example.com", "password": "secret123"})
    assert res.status_code == 200
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/auth/me", headers=headers).json()
    assert me["user"]["username"] == "Alice"
    assert me["user"]["email"] == "alice@example.com"  # normalized
    assert me["stats"] == {"repos_count": 0, "notebook_count": 0, "quizzes_passed": 0}

    # login works by username (any case) or email
    assert client.post("/api/auth/login", json={"login_id": "alice", "password": "secret123"}).status_code == 200
    assert client.post("/api/auth/login", json={"login_id": "ALICE@example.com", "password": "secret123"}).status_code == 200
    assert client.post("/api/auth/login", json={"login_id": "alice", "password": "wrong"}).status_code == 401

    # logout really revokes the token
    assert client.post("/api/auth/logout", headers=headers).json() == {"success": True}
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_register_validation_and_duplicates(client):
    def reg(u, e, p):
        return client.post("/api/auth/register", json={"username": u, "email": e, "password": p})

    assert reg("a", "a@x.com", "secret123").status_code == 400  # username too short
    assert reg("alice", "not-an-email", "secret123").status_code == 400
    assert reg("alice", "a@x.com", "123").status_code == 400  # password too short
    assert reg("alice", "a@x.com", "secret123").status_code == 200
    assert reg("ALICE", "other@x.com", "secret123").status_code == 400  # username case-insensitive
    assert reg("bob", "a@x.com", "secret123").status_code == 400  # duplicate email


def test_passwords_are_hashed_with_salt(client):
    from app.db import SessionLocal
    from app.models import User

    register(client, "carol")
    register(client, "dave")
    with SessionLocal() as db:
        carol, dave = db.query(User).order_by(User.username).all()
    assert "secret123" not in carol.password_hash
    assert carol.salt != dave.salt and carol.password_hash != dave.password_hash


def test_guest_login(client):
    data = client.post("/api/auth/guest").json()
    assert data["user"]["is_guest"] is True
    headers = {"Authorization": f"Bearer {data['token']}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_invalid_token_is_anonymous_not_error(client):
    res = client.get("/api/repo/user/list", headers={"Authorization": "Bearer nonsense"})
    assert res.status_code == 200 and res.json() == []
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_repositories_are_isolated_per_user(client, sample_repo, llm):
    alice, bob = register(client, "alice"), register(client, "bob")
    repo_id = connect(client, sample_repo, alice)

    assert [r["repo_id"] for r in client.get("/api/repo/user/list", headers=alice).json()] == [repo_id]
    assert client.get("/api/repo/user/list", headers=bob).json() == []
    assert client.get("/api/repo/user/list").json() == []  # anonymous

    for method, path, body in [
        ("get", f"/api/repo/{repo_id}/info", None),
        ("get", f"/api/repo/{repo_id}/onboarding", None),
        ("get", f"/api/repo/{repo_id}/flowchart", None),
        ("get", f"/api/repo/{repo_id}/graph", None),
        ("get", f"/api/repo/{repo_id}/chat/history", None),
        ("post", f"/api/repo/{repo_id}/file-details", {"path": "app/main.py"}),
        ("post", f"/api/repo/{repo_id}/chat", {"message": "hi"}),
        ("post", f"/api/repo/{repo_id}/assistant", {"message": "do it"}),
    ]:
        for who in (bob, {}):
            res = getattr(client, method)(path, headers=who, **({"json": body} if body else {}))
            assert res.status_code == 404, (method, path, who, res.status_code)
        ok = getattr(client, method)(path, headers=alice, **({"json": body} if body else {}))
        assert ok.status_code in (200, 502), (path, ok.status_code, ok.text)  # 502 = fake assistant unavailable

    assert client.get(f"/api/repo/{repo_id}/info", headers=alice).json()["name"] == "demo"


def test_notebook_is_isolated_and_editable_only_by_owner(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    note = client.post("/api/notebook", json={"concept": "Mine", "summary": "s"}, headers=alice).json()
    anon_note = client.post("/api/notebook", json={"concept": "Anon", "summary": "s"}).json()

    assert [e["concept"] for e in client.get("/api/notebook", headers=alice).json()] == ["Mine"]
    assert client.get("/api/notebook", headers=bob).json() == []
    assert [e["concept"] for e in client.get("/api/notebook").json()] == ["Anon"]  # not Alice's, and Bob doesn't see Anon

    for who in (bob, {}):
        assert client.put(f"/api/notebook/{note['id']}", json={"user_notes": "x"}, headers=who).status_code == 404
        assert client.delete(f"/api/notebook/{note['id']}", headers=who).status_code == 404
        assert client.post(f"/api/notebook/{note['id']}/favorite", headers=who).status_code == 404
    assert client.delete(f"/api/notebook/{anon_note['id']}", headers=alice).status_code == 404


def test_notebook_crud_search_and_favorites(client):
    h = register(client, "alice")
    a = client.post("/api/notebook", json={"concept": "Dependency injection", "summary": "passing deps in", "repo_name": "shop"}, headers=h).json()
    client.post("/api/notebook", json={"concept": "Caching", "summary": "memoize", "repo_name": "blog", "category": "change"}, headers=h)

    assert client.post("/api/notebook", json={"concept": " ", "summary": "x"}, headers=h).status_code == 400

    assert client.put(f"/api/notebook/{a['id']}", json={"user_notes": "remember this"}, headers=h).json()["user_notes"] == "remember this"
    assert [e["concept"] for e in client.get("/api/notebook?q=remember", headers=h).json()] == ["Dependency injection"]
    assert [e["concept"] for e in client.get("/api/notebook?category=change", headers=h).json()] == ["Caching"]
    assert [e["concept"] for e in client.get("/api/notebook?repo=shop", headers=h).json()] == ["Dependency injection"]

    assert client.post(f"/api/notebook/{a['id']}/favorite", headers=h).json()["is_favorite"] is True
    assert [e["concept"] for e in client.get("/api/notebook?favorites=true", headers=h).json()] == ["Dependency injection"]
    assert client.post(f"/api/notebook/{a['id']}/favorite", headers=h).json()["is_favorite"] is False

    assert client.delete(f"/api/notebook/{a['id']}", headers=h).json() == {"success": True}
    assert len(client.get("/api/notebook", headers=h).json()) == 1

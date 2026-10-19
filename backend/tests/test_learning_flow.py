"""The core loop: connect -> onboarding -> flowchart -> file walkthrough -> quiz -> notebook."""

import json

from tests.helpers import connect, register


def test_connect_reports_graph_and_rejects_bad_sources(client, sample_repo, tmp_path):
    res = client.post("/api/repo/connect", json={"source": str(sample_repo)})
    body = res.json()
    assert res.status_code == 200 and body["name"] == "demo" and body["node_count"] >= 5 and body["edge_count"] >= 3

    assert client.post("/api/repo/connect", json={"source": "   "}).status_code == 400
    assert client.post("/api/repo/connect", json={"source": str(tmp_path / "missing")}).status_code == 400

    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "notes.txt").write_text("no python")
    assert client.post("/api/repo/connect", json={"source": str(empty)}).status_code == 422


def test_onboarding_ai_result_is_cached(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    first = client.get(f"/api/repo/{repo_id}/onboarding").json()
    assert first["degraded"] is False and first["main_idea"] == "A demo project."
    assert first["learning_curve"] == {"easy": ["easy thing"], "hard": ["hard thing"]}
    client.get(f"/api/repo/{repo_id}/onboarding")
    assert llm.calls.count("onboarding") == 1  # second read came from the cache


def test_onboarding_falls_back_honestly_and_retries(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    llm.fail = "Gemini is overloaded right now."
    degraded = client.get(f"/api/repo/{repo_id}/onboarding").json()
    assert degraded["degraded"] is True
    assert "Gemini is overloaded" in degraded["notice"]
    # Facts come from disk (the README's real first paragraph), not invented prose:
    assert "tiny demo service" in degraded["main_idea"]
    assert any(t["name"] == "Python" for t in degraded["tech_stack"])
    assert degraded["learning_curve"] == {"easy": [], "hard": []}

    llm.fail = None  # the fallback must not have been cached
    healthy = client.get(f"/api/repo/{repo_id}/onboarding").json()
    assert healthy["degraded"] is False


def test_flowchart_edges_are_real_imports(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    fc = client.get(f"/api/repo/{repo_id}/flowchart").json()

    by_path = {n["file_path"]: n for n in fc["nodes"] if n["file_path"]}
    assert by_path["app/main.py"]["tier"] == "entrypoint"
    assert by_path["app/routers/items.py"]["tier"] == "router"
    assert by_path["app/services/store.py"]["tier"] == "service"
    assert by_path["app/models.py"]["tier"] == "model"
    assert by_path["app/main.py"]["summary"] == "Role of app/main.py"

    edges = {(e["source"], e["target"]) for e in fc["edges"]}
    assert ("node-app/main.py", "node-app/routers/items.py") in edges
    assert ("node-app/routers/items.py", "node-app/services/store.py") in edges
    assert ("node-app/services/store.py", "node-app/models.py") in edges
    # nothing invented: main never imports models directly
    assert ("node-app/main.py", "node-app/models.py") not in edges
    labels = {(e["source"], e["target"]): e["label"] for e in fc["edges"]}
    assert labels[("node-app/routers/items.py", "node-app/services/store.py")] == "imports save_item"

    external = {n["label"] for n in fc["nodes"] if n["tier"] == "external"}
    assert "SQLAlchemy" in external and "fastapi" not in {x.lower() for x in external}
    ids = {n["id"] for n in fc["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in fc["edges"])


def test_flowchart_without_ai_uses_docstrings(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    llm.fail = "down"
    fc = client.get(f"/api/repo/{repo_id}/flowchart").json()
    assert fc["degraded"] is True and "down" in fc["notice"]
    assert {n["summary"] for n in fc["nodes"] if n["file_path"] == "app/main.py"} == {"App entrypoint."}


def test_file_details_validates_sections_and_hides_answers(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    res = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/routers/items.py"})
    data = res.json()
    assert res.status_code == 200 and data["degraded"] is False
    total = data["total_lines"]

    # AI's bogus ranges were clamped/dropped: every range is real, ordered, inside the file
    secs = data["line_sections"]
    assert [s["title"] for s in secs] == ["Setup", "Rest"]
    assert all(1 <= s["start_line"] <= s["end_line"] <= total for s in secs)

    assert len(data["quizzes"]) == 4
    for q in data["quizzes"]:
        # no answer, explanation or per-option reasoning leaks before the learner has answered
        assert q["review"] is None and q["hint"] is None and q["attempts"] == 0
        assert not {"correct_index", "explanation", "option_notes", "option_explanations"} & set(q)
        assert len(q["options"]) == 4


def test_file_details_cached_until_file_changes(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    path = {"path": "app/models.py"}
    first = client.post(f"/api/repo/{repo_id}/file-details", json=path).json()
    second = client.post(f"/api/repo/{repo_id}/file-details", json=path).json()
    assert llm.calls.count("file") == 1
    assert [q["id"] for q in first["quizzes"]] == [q["id"] for q in second["quizzes"]]  # stable ids

    (sample_repo / "app" / "models.py").write_text('"""Changed."""\n\nx = 1\ny = 2\nz = 3\n')
    third = client.post(f"/api/repo/{repo_id}/file-details", json=path).json()
    assert llm.calls.count("file") == 2
    assert [q["id"] for q in third["quizzes"]] != [q["id"] for q in first["quizzes"]]


def test_file_details_path_safety(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    for bad in ["../secret.txt", "../../etc/passwd", "app/../../x.py"]:
        assert client.post(f"/api/repo/{repo_id}/file-details", json={"path": bad}).status_code in (400, 404)
    assert client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/nope.py"}).status_code == 404
    assert client.post(f"/api/repo/{repo_id}/file-details", json={"path": ".git/config"}).status_code in (400, 404)


def test_file_details_degrades_to_real_structure(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    llm.fail = "AI down"
    data = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}).json()
    assert data["degraded"] is True and "AI down" in data["notice"]
    assert data["quizzes"] == []  # never canned filler questions
    assert data["overview"] == "Data models."  # the module's own docstring
    titles = [s["title"] for s in data["line_sections"]]
    assert "class Item" in titles
    item = next(s for s in data["line_sections"] if s["title"] == "class Item")
    assert (item["start_line"], item["end_line"]) == (4, 6)  # the class's true line range


def _first_quiz(client, repo_id, path="app/models.py"):
    return client.post(f"/api/repo/{repo_id}/file-details", json={"path": path}).json()["quizzes"][0]


def test_answering_is_verified_server_side_and_credits_notebook_once(client, sample_repo, llm):
    h = register(client, "alice")
    repo_id = connect(client, sample_repo, h)
    quizzes = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}, headers=h).json()["quizzes"]
    quiz = quizzes[0]
    ans = f"/api/quiz/{quiz['id']}/answer"
    wrong_ids = [i for i, o in enumerate(quiz["options"]) if not o.startswith("right")]
    right_idx = next(i for i, o in enumerate(quiz["options"]) if o.startswith("right"))

    # First wrong try: taught, not told. The answer stays hidden; they get why *their* option
    # is wrong and a hint.
    first = client.post(ans, json={"selected_index": wrong_ids[0]}, headers=h).json()
    assert first["correct"] is False and first["final"] is False and first["correct_index"] is None
    assert first["explanation"] is None and first["resource"] is None and first["attempts_left"] == 1
    assert first["option_feedback"].startswith("no-") and first["hint"] == "hint 0"
    assert client.get("/api/notebook", headers=h).json() == []  # a wrong answer earns nothing
    assert client.post(ans, json={"selected_index": wrong_ids[0]}, headers=h).status_code == 400  # same option again

    # Second try, correct: credited once.
    second = client.post(ans, json={"selected_index": right_idx}, headers=h).json()
    assert second["correct"] is True and second["final"] is True and second["saved_to_notebook"] is True
    assert second["explanation"] and second["correct_index"] == right_idx and second["option_feedback"] == "yes 0"
    again = client.post(ans, json={"selected_index": right_idx}, headers=h).json()
    assert again["correct"] is True and again["saved_to_notebook"] is False  # no duplicate credit

    entries = client.get("/api/notebook", headers=h).json()
    assert len(entries) == 1
    assert entries[0]["repo_name"] == "demo"  # the real repo name, not an id
    assert entries[0]["file_path"] == "app/models.py" and entries[0]["category"] == "file_walkthrough"
    assert client.get("/api/auth/me", headers=h).json()["stats"]["quizzes_passed"] == 1

    # Two wrong tries: now everything is revealed, with something to read (FR9) - and clicking
    # the right option afterwards earns no credit, because the answer has been shown.
    other = quizzes[1]
    url = f"/api/quiz/{other['id']}/answer"
    bad = [i for i, o in enumerate(other["options"]) if not o.startswith("right")]
    good = next(i for i, o in enumerate(other["options"]) if o.startswith("right"))
    client.post(url, json={"selected_index": bad[0]}, headers=h)
    final = client.post(url, json={"selected_index": bad[1]}, headers=h).json()
    assert final["correct"] is False and final["final"] is True and final["correct_index"] == good
    assert final["explanation"] == "because 1"
    assert final["resource"]["url"].startswith("https://www.google.com/search?q=python+topic+1")
    assert "resource" not in llm.calls  # written with the question: no extra AI call, no waiting
    late = client.post(url, json={"selected_index": good}, headers=h).json()
    assert late["correct"] is False and late["saved_to_notebook"] is False
    assert len(client.get("/api/notebook", headers=h).json()) == 1

    # Progress survives a reload: the same questions come back in the state they were left in.
    reloaded = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}, headers=h).json()["quizzes"]
    assert reloaded[0]["review"]["correct"] is True and reloaded[1]["review"]["correct"] is False
    assert reloaded[1]["review"]["selected_index"] == bad[1] and reloaded[2]["review"] is None


def test_answer_rejects_bad_index_and_other_users(client, sample_repo, llm):
    alice, bob = register(client, "alice"), register(client, "bob")
    repo_id = connect(client, sample_repo, alice)
    quiz = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}, headers=alice).json()["quizzes"][0]
    url = f"/api/quiz/{quiz['id']}/answer"
    assert client.post(url, json={"selected_index": 9}, headers=alice).status_code == 400
    assert client.post(url, json={"selected_index": -1}, headers=alice).status_code == 400
    assert client.post(url, json={"selected_index": 0}, headers=bob).status_code == 404
    assert client.post(url, json={"selected_index": 0}).status_code == 404
    assert client.post(f"/api/quiz/{quiz['id']}/retry", headers=bob).status_code == 404
    assert client.post("/api/quiz/doesnotexist/answer", json={"selected_index": 0}, headers=alice).status_code == 404


def test_wrong_answer_still_works_when_resource_ai_fails(client, sample_repo, llm):
    """Questions saved before resources were generated alongside them ask the AI at answer time;
    if that fails, the learner still gets their feedback."""
    from app.db import SessionLocal
    from app.models import Quiz

    repo_id = connect(client, sample_repo)
    quiz = _first_quiz(client, repo_id)
    with SessionLocal() as db:
        db.get(Quiz, quiz["id"]).resource_json = None
        db.commit()
    llm.overrides["resource"] = lambda _p: "not json at all"
    bad = [i for i, o in enumerate(quiz["options"]) if not o.startswith("right")]
    client.post(f"/api/quiz/{quiz['id']}/answer", json={"selected_index": bad[0]})
    res = client.post(f"/api/quiz/{quiz['id']}/answer", json={"selected_index": bad[1]})
    body = res.json()
    assert res.status_code == 200 and body["correct"] is False and body["final"] and body["resource"] is None

    llm.overrides.pop("resource")  # ...and when the AI is available, they get one
    quiz2 = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}).json()["quizzes"][1]
    with SessionLocal() as db:
        db.get(Quiz, quiz2["id"]).resource_json = None
        db.commit()
    bad = [i for i, o in enumerate(quiz2["options"]) if not o.startswith("right")]
    client.post(f"/api/quiz/{quiz2['id']}/answer", json={"selected_index": bad[0]})
    body = client.post(f"/api/quiz/{quiz2['id']}/answer", json={"selected_index": bad[1]}).json()
    assert body["resource"]["title"] == "Read this"


def test_retry_gives_a_fresh_question_on_the_same_concept(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    quiz = _first_quiz(client, repo_id)
    llm.overrides["quiz"] = {"quizzes": llm.quiz(2, " fresh")}
    fresh = client.post(f"/api/quiz/{quiz['id']}/retry").json()
    assert fresh["id"] != quiz["id"] and fresh["question"] == "Question 0 fresh?"
    assert fresh["concept"] == quiz["concept"]
    assert "correct_index" not in fresh and fresh["review"] is None

    # the fresh question takes the old one's place when the file is reopened
    ids = [q["id"] for q in client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}).json()["quizzes"]]
    assert fresh["id"] in ids and quiz["id"] not in ids and len(ids) == 4

    llm.fail = "quota"
    assert client.post(f"/api/quiz/{quiz['id']}/retry").status_code == 502


def test_malformed_ai_quizzes_are_rejected_not_shown(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    bad = [
        {"concept": "c", "question": "q1", "options": ["a", "a", "b", "c"], "correct_index": 0},  # duplicate options
        {"concept": "c", "question": "q2", "options": ["a", "b", "c"], "correct_index": 0},  # only 3 options
        {"concept": "c", "question": "q3", "options": ["a", "b", "c", "d"], "correct_index": 7},  # index out of range
        {"concept": "c", "question": "q4", "options": ["a", "b", "c", "d"], "correct_index": True},  # bool, not int
    ]
    good = llm.quiz(1)[0]
    llm.overrides["file"] = {
        "overview": "o", "line_sections": [{"start_line": 1, "end_line": 2, "title": "t", "explanation": "e"}],
        "quizzes": bad + [good],
    }
    llm.overrides["quiz"] = lambda _p: "{}"  # the top-up call finds nothing usable either
    data = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}).json()
    assert data["quizzes"] == [] and "Quiz unavailable" in data["notice"]


def test_options_are_shuffled_without_changing_which_is_correct(client, sample_repo, llm):
    from app.services.quiz_service import clean_quiz

    raw = {"concept": "c", "question": "q", "options": ["RIGHT", "b", "c", "d"], "correct_index": 0}
    positions = set()
    for _ in range(60):
        q = clean_quiz(dict(raw))
        assert q["options"][q["correct_index"]] == "RIGHT"
        positions.add(q["correct_index"])
    assert len(positions) > 1  # not always position 0


def test_chat_uses_code_and_history_and_persists_only_real_replies(client, sample_repo, llm):
    seen = {}
    llm.overrides["chat"] = lambda p: (seen.update(prompt=p) or json.dumps({"reply": "R1", "suggested_followups": ["f"]}))
    h = register(client, "alice")
    repo_id = connect(client, sample_repo, h)
    ctx = {"context_type": "quiz_discussion", "file_path": "app/models.py", "question": "Q?", "user_answer": "mine", "correct_answer": "theirs"}

    res = client.post(f"/api/repo/{repo_id}/chat", json={"message": "why?", "context": ctx}, headers=h)
    assert res.json() == {"reply": "R1", "suggested_followups": ["f"], "sources": ["app/models.py"]}
    assert "class Item" in seen["prompt"] and "Learner chose (wrong): mine" in seen["prompt"] and "Correct answer: theirs" in seen["prompt"]

    client.post(f"/api/repo/{repo_id}/chat", json={"message": "and then?"}, headers=h)
    assert "Learner: why?" in seen["prompt"] and "Tutor: R1" in seen["prompt"]  # remembers the conversation

    llm.fail = "quota"
    failed = client.post(f"/api/repo/{repo_id}/chat", json={"message": "lost"}, headers=h)
    assert failed.status_code == 502  # an honest error, not a canned "Great question!" reply
    history = client.get(f"/api/repo/{repo_id}/chat/history", headers=h).json()
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]  # the failed turn left no orphan
    assert client.post(f"/api/repo/{repo_id}/chat", json={"message": "  "}, headers=h).status_code == 400


def test_self_sample_is_a_fresh_git_copy_per_connection(client, llm):
    import subprocess
    from pathlib import Path

    from app.services.github_service import _PROJECT_ROOT

    samples = client.get("/api/repo/samples").json()
    assert {"requests", "nanogpt"} <= {s["name"].split(" ")[0].lower() for s in samples}
    me = next(s for s in samples if s["id"] == "sample-codeliteracy")
    assert me["source"] == "sample:codeliteracy"  # a token, never the live project path

    paths = []
    for _ in range(2):
        res = client.post("/api/repo/connect", json={"source": me["source"]})
        assert res.status_code == 200, res.text
        info = client.get(f"/api/repo/{res.json()['repo_id']}/info").json()
        assert info["source"] == "CodeLiteracy (safe copy)" and info["name"] == "codeliteracy"
        from app.db import SessionLocal
        from app.models import Repository

        with SessionLocal() as db:
            paths.append(Path(db.get(Repository, res.json()["repo_id"]).local_path))

    assert paths[0] != paths[1]  # one session's edits can never leak into another's
    for p in paths:
        assert p.resolve() != _PROJECT_ROOT and (_PROJECT_ROOT / "backend") not in p.resolve().parents
        assert (p / "app" / "main.py").is_file() and not list(p.rglob("__pycache__"))
        log = subprocess.run(["git", "log", "--format=%an|%s"], cwd=p, capture_output=True, text=True).stdout
        assert log.strip() == "CodeLiteracy|Snapshot of CodeLiteracy for exploration"  # so AI changes get committed on top
        assert subprocess.run(["git", "status", "--porcelain"], cwd=p, capture_output=True, text=True).stdout == ""

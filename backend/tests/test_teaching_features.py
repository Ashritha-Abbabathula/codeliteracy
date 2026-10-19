"""The features that make the answers *proper* and the app teach: a tutor grounded in the real
repository, explanations of any selected lines, a file browser with progress, a reading order,
and an assistant that edits surgically, shows its work, and can be undone."""

import json
import subprocess

import httpx
import pytest

from app.services import assistant_service, llm_client
from app.services.assistant_service import run_assistant
from app.services.llm_client import LLMCallError
from app.services.repo_context import find_relevant_files, numbered_excerpt, repo_digest
from tests.helpers import connect, register
from tests.test_assistant_and_units import NEW_MODELS, SUBMIT, call, reply, scripted  # noqa: F401


# ---- the tutor answers from the repository, not from its name ---------------------------


def test_general_question_is_answered_from_repo_files(client, sample_repo, llm):
    seen = {}
    llm.overrides["chat"] = lambda p: (seen.update(prompt=p) or json.dumps({"reply": "R", "suggested_followups": []}))
    repo_id = connect(client, sample_repo)

    # No file open, no context at all: the tutor must still be shown the repo.
    res = client.post(f"/api/repo/{repo_id}/chat", json={"message": "How does save_item work?"}).json()
    prompt = seen["prompt"]
    assert "app/services/store.py" in prompt and "app/routers/items.py" in prompt  # the file list
    assert "def save_item(name)" in prompt  # outline of a key module
    assert "return Item(name=name)" in prompt  # the relevant file's actual code, found by search
    assert res["sources"][0] == "app/services/store.py"

    # A vague question finds no particular file, but still carries the whole-repo digest.
    res = client.post(f"/api/repo/{repo_id}/chat", json={"message": "What should I read first?"}).json()
    assert res["sources"] == [] and "Key modules" in seen["prompt"]


def test_tutor_focuses_on_selected_lines_of_a_long_file(client, tmp_path, llm):
    repo = tmp_path / "big"
    repo.mkdir()
    body = "\n".join(f"def f{i}():\n    return {i}\n" for i in range(400))  # 1,200 lines
    (repo / "big.py").write_text(body)
    seen = {}
    llm.overrides["chat"] = lambda p: (seen.update(prompt=p) or json.dumps({"reply": "R", "suggested_followups": []}))
    repo_id = connect(client, repo)
    ctx = {"context_type": "file_explainer", "file_path": "big.py", "start_line": 1000, "end_line": 1001}
    client.post(f"/api/repo/{repo_id}/chat", json={"message": "what is this?", "context": ctx})
    # The selection is deep in the file: it must be in the prompt (the old code sent only the
    # first 9,000 characters, so the tutor could not see what was being asked about).
    assert "1000: def f333():" in seen["prompt"] and "1001:     return 333" in seen["prompt"]
    assert "they selected lines 1000-1001" in seen["prompt"]


def test_chat_history_can_be_cleared(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    client.post(f"/api/repo/{repo_id}/chat", json={"message": "hello"})
    assert len(client.get(f"/api/repo/{repo_id}/chat/history").json()) == 2
    assert client.delete(f"/api/repo/{repo_id}/chat/history").json() == {"success": True}
    assert client.get(f"/api/repo/{repo_id}/chat/history").json() == []


def test_repo_context_helpers(sample_repo):
    hits = find_relevant_files(sample_repo, "where is the Item class defined?")
    assert hits[0]["path"] == "app/models.py" and 4 in hits[0]["lines"]
    assert find_relevant_files(sample_repo, "what is this?") == []  # nothing but stopwords
    assert find_relevant_files(sample_repo, "explain app/routers/items.py")[0]["path"] == "app/routers/items.py"

    digest = repo_digest(sample_repo)
    assert "app/main.py" in digest and "class Item" in digest
    assert numbered_excerpt(sample_repo, "../outside.py") is None  # never reads outside the repo
    assert numbered_excerpt(sample_repo, ".git/config") is None


# ---- explain exactly these lines ---------------------------------------------------------


def test_explain_lines_validates_caches_and_reports_errors(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    url = f"/api/repo/{repo_id}/explain-lines"
    res = client.post(url, json={"path": "app/models.py", "start_line": 6, "end_line": 4})  # reversed is fine
    data = res.json()
    assert res.status_code == 200 and (data["start_line"], data["end_line"]) == (4, 6)
    # notes outside the selection are dropped; the rest come back in order
    assert [(n["start_line"], n["end_line"]) for n in data["notes"]] == [(4, 4), (5, 6)]
    assert data["concepts"] == [{"term": "constructor", "meaning": "Runs when an object is created."}]
    assert data["cached"] is False

    calls = llm.calls.count("lines")
    assert client.post(url, json={"path": "app/models.py", "start_line": 4, "end_line": 6}).json()["cached"] is True
    assert llm.calls.count("lines") == calls  # no second AI call for the same lines

    (sample_repo / "app" / "models.py").write_text("x = 1\ny = 2\nz = 3\nw = 4\nv = 5\nu = 6\n")
    assert client.post(url, json={"path": "app/models.py", "start_line": 4, "end_line": 6}).json()["cached"] is False

    assert client.post(url, json={"path": "app/models.py", "start_line": 50, "end_line": 60}).status_code == 400
    (sample_repo / "app" / "long.py").write_text("x = 1\n" * 300)
    too_many = client.post(url, json={"path": "app/long.py", "start_line": 1, "end_line": 300})
    assert too_many.status_code == 400 and "at most 80 lines" in too_many.json()["detail"]
    assert client.post(url, json={"path": "../secret.py", "start_line": 1, "end_line": 2}).status_code == 400
    assert client.post(url, json={"path": "nope.py", "start_line": 1, "end_line": 2}).status_code == 404

    llm.fail = "quota"  # an honest error, never an invented explanation
    res = client.post(url, json={"path": "app/models.py", "start_line": 1, "end_line": 2})
    assert res.status_code == 502 and "quota" in res.json()["detail"]


def test_long_files_get_their_real_structure_below_the_ai_walkthrough(client, tmp_path, llm):
    repo = tmp_path / "long"
    repo.mkdir()
    (repo / "long.py").write_text("\n".join(f'def f{i}():\n    """Doc {i}."""\n    return {i}\n' for i in range(250)))  # 1,000 lines
    repo_id = connect(client, repo)
    data = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "long.py"}).json()
    ai = [s for s in data["line_sections"] if not s.get("needs_explanation")]
    rest = [s for s in data["line_sections"] if s.get("needs_explanation")]
    assert ai and max(s["end_line"] for s in ai) <= 600
    assert rest and min(s["start_line"] for s in rest) > 600 and rest[-1]["end_line"] == 999
    assert rest[0]["title"].startswith("def f") and rest[0]["explanation"].startswith("Doc ")
    assert "long file" in data["notice"]
    assert data["key_concepts"] == [{"term": "router", "meaning": "Maps URLs to functions."}]


# ---- file browser, progress, reading order -----------------------------------------------


def test_files_and_progress_track_what_the_learner_has_done(client, sample_repo, llm):
    h = register(client, "alice")
    repo_id = connect(client, sample_repo, h)
    files = {f["path"]: f for f in client.get(f"/api/repo/{repo_id}/files", headers=h).json()}
    assert {"app/main.py", "app/models.py", "README.md"} <= set(files)  # every file, not just flowchart nodes
    assert files["app/models.py"]["kind"] == "python" and files["README.md"]["kind"] == "other"
    assert not any(f["explored"] for f in files.values())
    assert client.get(f"/api/repo/{repo_id}/files").status_code == 404  # someone else's repo

    quiz = client.post(f"/api/repo/{repo_id}/file-details", json={"path": "app/models.py"}, headers=h).json()["quizzes"][0]
    right = next(i for i, o in enumerate(quiz["options"]) if o.startswith("right"))
    client.post(f"/api/quiz/{quiz['id']}/answer", json={"selected_index": right}, headers=h)

    entry = {f["path"]: f for f in client.get(f"/api/repo/{repo_id}/files", headers=h).json()}["app/models.py"]
    assert entry["explored"] and entry["questions"] == 4 and entry["solved"] == 1
    progress = client.get(f"/api/repo/{repo_id}/progress", headers=h).json()
    assert progress == {
        "files_total": 4, "files_explored": 1, "questions_total": 4,
        "questions_answered": 1, "questions_solved": 1, "changes_made": 0,
    }


def test_learning_path_only_points_at_real_files(client, sample_repo, llm):
    repo_id = connect(client, sample_repo)
    path = client.get(f"/api/repo/{repo_id}/onboarding").json()["learning_path"]
    # exact path kept; "services/store.py" resolved to the one real file with that name; the
    # invented file dropped
    assert [s["file_path"] for s in path] == ["app/models.py", "app/services/store.py"]

    # Without the AI, the reading order comes from the dependency graph: foundations first,
    # the entry point last.
    llm.fail = "down"
    other = connect(client, sample_repo)
    fallback = client.get(f"/api/repo/{other}/onboarding").json()["learning_path"]
    order = [s["file_path"] for s in fallback]
    assert order[0] == "app/models.py" and order[-1] == "app/main.py" and all(s["why"] for s in fallback)


def test_onboarding_cached_by_an_older_version_gains_a_learning_path(client, sample_repo, llm):
    from app.db import SessionLocal
    from app.models import Repository

    repo_id = connect(client, sample_repo)
    with SessionLocal() as db:
        db.get(Repository, repo_id).onboarding_json = json.dumps({
            "greeting": "Hi", "main_idea": "Old.", "tech_stack": [], "learning_curve": {"easy": [], "hard": []},
            "folder_guide": [], "transition_message": "",
        })
        db.commit()
    data = client.get(f"/api/repo/{repo_id}/onboarding").json()
    assert data["main_idea"] == "Old." and data["learning_path"] and "onboarding" not in llm.calls


# ---- the assistant: surgical edits, visible work, undo, history --------------------------


def test_edit_file_changes_one_place_and_explains_failures(sample_repo, scripted):
    fake = scripted(
        reply(call("read_file", path="app/models.py")),
        reply(call("edit_file", path="app/models.py", old_text="self.name = nope", new_text="x")),  # not in file
        reply(call("edit_file", path="app/services/store.py", old_text="Item", new_text="Thing")),  # ambiguous
        reply(call("edit_file", path="app/models.py", old_text="        self.name = name", new_text="        self.name = (")),  # breaks syntax
        reply(call("edit_file", path="app/missing.py", old_text="a", new_text="b")),
        reply(call("edit_file", path="app/models.py", old_text="        self.name = name",
                   new_text='        if not name:\n            raise ValueError("name required")\n        self.name = name')),
        reply(SUBMIT),
    )
    result = run_assistant(str(sample_repo), "validate names")
    assert "was not found" in fake.tool_results[1] and "occurs 2 times" in fake.tool_results[2]
    assert "syntax error" in fake.tool_results[3] and "does not exist" in fake.tool_results[4]
    assert fake.tool_results[5] == "Edited app/models.py"
    assert (sample_repo / "app" / "models.py").read_text() == NEW_MODELS  # the rest of the file untouched
    assert (sample_repo / "app" / "services" / "store.py").read_text().count("Item") == 2  # failed edits wrote nothing
    assert result["files_changed"] == ["app/models.py"] and result["diffs"][0]["added"] == 2

    log = [(a["kind"], a["label"], a["ok"]) for a in result["activity"]]
    assert log == [
        ("read", "Read app/models.py", True),
        ("error", "Rejected a change to app/models.py", False),
        ("edit", "Edited app/models.py", True),
    ]


def test_assistant_reports_its_teaching_notes(sample_repo, scripted):
    scripted(
        reply(call("list_files", path="")),
        reply(call("search_files", query="Item")),
        reply(call("write_file", path="app/models.py", content=NEW_MODELS)),
        reply(call("submit_result", summary="S.", concept="validation", concept_explanation="Checking input early.",
                   verify="Run Item('') and expect ValueError.", steps=[{"action": "a", "explanation": "e"}])),
    )
    result = run_assistant(str(sample_repo), "validate")
    assert result["concept_explanation"] == "Checking input early." and "ValueError" in result["verify"]
    kinds = [a["kind"] for a in result["activity"]]
    assert kinds == ["list", "search", "edit"]
    assert result["activity"][1]["label"] == "Searched for “Item”" and "matching line" in result["activity"][1]["detail"]


def _change(client, repo_id, scripted, headers=None, content=NEW_MODELS, path="app/models.py"):
    scripted(reply(call("write_file", path=path, content=content)), reply(SUBMIT))
    res = client.post(f"/api/repo/{repo_id}/assistant", json={"message": "validate"}, headers=headers or {})
    assert res.status_code == 200, res.text
    return res.json()


def test_change_history_survives_a_reload_with_quiz_progress(client, sample_repo, scripted, llm):
    h = register(client, "alice")
    repo_id = connect(client, sample_repo, h)
    data = _change(client, repo_id, scripted, h)
    assert data["can_undo"] is True and data["reverted"] is False and data["request"] == "validate"
    assert [a["label"] for a in data["activity"]] == ["Rewrote app/models.py"]

    quiz = data["quizzes"][0]
    right = next(i for i, o in enumerate(quiz["options"]) if o.startswith("right"))
    client.post(f"/api/quiz/{quiz['id']}/answer", json={"selected_index": right}, headers=h)

    history = client.get(f"/api/repo/{repo_id}/changes", headers=h).json()
    assert len(history) == 1 and history[0]["change_id"] == data["change_id"]
    assert history[0]["diffs"][0]["path"] == "app/models.py" and history[0]["steps"]
    assert history[0]["quizzes"][0]["review"]["correct"] is True and history[0]["quizzes"][1]["review"] is None
    assert client.get(f"/api/repo/{repo_id}/changes").status_code == 404  # not yours


def test_undo_restores_the_files_and_commits(client, sample_repo, scripted, llm):
    original = (sample_repo / "app" / "models.py").read_text()
    repo_id = connect(client, sample_repo)
    data = _change(client, repo_id, scripted)
    assert (sample_repo / "app" / "models.py").read_text() == NEW_MODELS

    res = client.post(f"/api/changes/{data['change_id']}/undo")
    body = res.json()
    assert res.status_code == 200 and body["restored"] == ["app/models.py"] and body["commit_sha"]
    assert (sample_repo / "app" / "models.py").read_text() == original
    log = subprocess.run(["git", "log", "--format=%s", "-2"], cwd=sample_repo, capture_output=True, text=True).stdout.splitlines()
    assert log[0].startswith("CodeLiteracy: undo") and log[1].startswith("CodeLiteracy: Added validation.")

    assert client.post(f"/api/changes/{data['change_id']}/undo").status_code == 409  # only once
    history = client.get(f"/api/repo/{repo_id}/changes").json()
    assert history[0]["reverted"] is True and history[0]["can_undo"] is False
    assert client.post("/api/changes/nope/undo").status_code == 404


def test_undo_refuses_to_overwrite_later_work_and_removes_created_files(client, sample_repo, scripted, llm):
    repo_id = connect(client, sample_repo)
    data = _change(client, repo_id, scripted)
    (sample_repo / "app" / "models.py").write_text(NEW_MODELS + "\n# my own later edit\n")
    res = client.post(f"/api/changes/{data['change_id']}/undo")
    assert res.status_code == 409 and "changed again" in res.json()["detail"]
    assert "# my own later edit" in (sample_repo / "app" / "models.py").read_text()  # nothing was lost
    assert client.get(f"/api/repo/{repo_id}/changes").json()[0]["can_undo"] is False

    created = _change(client, repo_id, scripted, content="x = 1\n", path="app/extra.py")
    assert (sample_repo / "app" / "extra.py").is_file()
    assert client.post(f"/api/changes/{created['change_id']}/undo").status_code == 200
    assert not (sample_repo / "app" / "extra.py").exists()
    status = subprocess.run(["git", "status", "--porcelain", "app/extra.py"], cwd=sample_repo, capture_output=True, text=True).stdout
    assert status == ""  # the removal was committed too


def test_a_change_refreshes_what_was_derived_from_the_old_code(client, sample_repo, scripted, llm):
    repo_id = connect(client, sample_repo)
    client.get(f"/api/repo/{repo_id}/flowchart")
    before = llm.calls.count("summaries")
    edges = lambda: {(e["source"], e["target"]) for e in client.get(f"/api/repo/{repo_id}/graph").json()["edges"]}  # noqa: E731
    assert ("app/models.py", "app/services/store.py") not in edges()

    _change(client, repo_id, scripted, content='"""Data models."""\nfrom app.services import store\n\n\nclass Item:\n    pass\n')
    assert ("app/models.py", "app/services/store.py") in edges()  # the graph follows the code
    client.get(f"/api/repo/{repo_id}/flowchart")
    assert llm.calls.count("summaries") == before + 1  # the flowchart was rebuilt, not served stale


# ---- failure modes a learner will actually hit --------------------------------------------


def test_no_internet_is_a_clear_message_not_a_crash(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)

    class Offline:
        class models:
            @staticmethod
            def generate_content(**_kw):
                raise httpx.ConnectError("getaddrinfo failed")

    with pytest.raises(LLMCallError, match="internet connection"):
        llm_client.generate_with_retry(Offline(), model="m", contents="c")


def test_assistant_endpoint_reports_being_offline(client, sample_repo, monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)

    def offline(*_a, **_kw):
        raise LLMCallError("Couldn't reach Gemini. Check this computer's internet connection.")

    monkeypatch.setattr(assistant_service, "generate_with_retry", offline)
    repo_id = connect(client, sample_repo)
    res = client.post(f"/api/repo/{repo_id}/assistant", json={"message": "fix it"})
    assert res.status_code == 502 and "internet connection" in res.json()["detail"]
    assert client.post(f"/api/repo/{repo_id}/assistant", json={"message": "x" * 2001}).status_code == 400

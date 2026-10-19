"""The AI assistant's tool loop (with a scripted fake Gemini), git safety, and unit tests for
the smaller pieces that the learning flow depends on."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types
from google.genai.errors import APIError

from app.services import assistant_service, llm_client
from app.services.assistant_service import AssistantError, run_assistant
from app.services.diff_utils import build_file_diff
from app.services.github_service import RepoConnectionError, commit_changes, connect_repository
from tests.helpers import connect, register


# ---- scripted fake Gemini for the assistant tool loop ----------------------------------


def call(name: str, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def reply(*parts):
    return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=list(parts)))])


class ScriptedGemini:
    """generate_with_retry replacement: returns the next scripted reply and records what the
    assistant was told after each tool call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.tool_results: list[str] = []

    def __call__(self, client, **kwargs):
        contents = kwargs["contents"]
        last = contents[-1]
        if last.role == "user" and last.parts and last.parts[0].function_response:
            self.tool_results += [p.function_response.response["result"] for p in last.parts]
        return self.replies.pop(0)


@pytest.fixture
def scripted(monkeypatch):
    def install(*replies):
        fake = ScriptedGemini(*replies)
        monkeypatch.setattr(assistant_service, "generate_with_retry", fake)
        return fake

    return install


SUBMIT = call(
    "submit_result", summary="Added validation.", concept="input validation",
    steps=[{"action": "Edited app/models.py", "explanation": "Because names must not be empty."}],
)

NEW_MODELS = '"""Data models."""\n\n\nclass Item:\n    def __init__(self, name):\n        if not name:\n            raise ValueError("name required")\n        self.name = name\n'


def test_assistant_edits_file_and_reports_real_diff(sample_repo, scripted):
    fake = scripted(
        reply(call("list_files", path="/")),
        reply(call("search_files", query="class Item")),
        reply(call("read_file", path="app/models.py")),
        reply(call("write_file", path="app/models.py", content=NEW_MODELS)),
        reply(SUBMIT),
    )
    result = run_assistant(str(sample_repo), "validate names")

    assert "app/" in fake.tool_results[0]  # list_files("/") means the repo root, not the filesystem root
    assert "app/models.py:4: class Item:" in fake.tool_results[1]
    assert result["files_changed"] == ["app/models.py"]
    assert result["concept"] == "input validation" and result["steps"][0]["explanation"].startswith("Because")

    diff = result["diffs"][0]
    assert diff["added"] == 2 and diff["removed"] == 0 and diff["is_new_file"] is False
    added = [ln["text"] for ln in diff["lines"] if ln["kind"] == "add"]
    assert added == ["        if not name:", '            raise ValueError("name required")']
    assert (sample_repo / "app" / "models.py").read_text() == NEW_MODELS


def test_assistant_refuses_syntax_errors_and_escapes(sample_repo, scripted):
    fake = scripted(
        reply(call("write_file", path="app/models.py", content="def broken(:\n    pass\n"),
              call("read_file", path="../../etc/passwd"),
              call("write_file", path="../outside.py", content="x = 1\n"),
              call("read_file", path=".git/config")),
        reply(call("write_file", path="app/models.py", content=NEW_MODELS)),
        reply(SUBMIT),
    )
    result = run_assistant(str(sample_repo), "go")

    assert "syntax error on line 1" in fake.tool_results[0]
    assert "outside the repo" in fake.tool_results[1] and "outside the repo" in fake.tool_results[2]
    assert ".git" in fake.tool_results[3]
    assert not (sample_repo.parent / "outside.py").exists()
    assert (sample_repo / "app" / "models.py").read_text() == NEW_MODELS  # the broken version never landed
    assert result["files_changed"] == ["app/models.py"]


def test_assistant_survives_malformed_tool_calls(sample_repo, scripted):
    fake = scripted(
        reply(call("read_file"), call("write_file", path="app/x.py"), call("nonexistent_tool", a=1)),
        reply(call("write_file", path="app/models.py", content=NEW_MODELS)),
        reply(SUBMIT),
    )
    result = run_assistant(str(sample_repo), "go")
    assert all(r.startswith("Error") for r in fake.tool_results[:3])
    assert result["files_changed"] == ["app/models.py"]


def test_assistant_rejects_a_run_that_changed_nothing(sample_repo, scripted):
    scripted(reply(call("read_file", path="app/models.py")), reply(SUBMIT))
    with pytest.raises(AssistantError, match="didn't change any files"):
        run_assistant(str(sample_repo), "explain models")


def test_assistant_rewriting_identical_content_is_not_a_change(sample_repo, scripted):
    same = (sample_repo / "app" / "models.py").read_text()
    fake = scripted(reply(call("write_file", path="app/models.py", content=same)), reply(SUBMIT))
    with pytest.raises(AssistantError, match="didn't change any files"):
        run_assistant(str(sample_repo), "go")
    assert "No change" in fake.tool_results[0]


def test_assistant_gives_up_after_too_many_steps(sample_repo, scripted):
    scripted(*[reply(call("list_files", path="")) for _ in range(assistant_service.MAX_TOOL_ITERATIONS)])
    with pytest.raises(AssistantError, match="too many steps"):
        run_assistant(str(sample_repo), "loop forever")


def test_assistant_preserves_crlf_line_endings(tmp_path, scripted):
    repo = tmp_path / "crlf"
    repo.mkdir()
    (repo / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    scripted(reply(call("write_file", path="a.py", content="x = 1\ny = 3\n")), reply(SUBMIT))
    run_assistant(str(repo), "go")
    assert (repo / "a.py").read_bytes() == b"x = 1\r\ny = 3\r\n"  # not silently converted to LF (or a whole-file diff)


def test_assistant_can_create_new_files(tmp_path, scripted):
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n")
    scripted(reply(call("write_file", path="pkg/new.py", content="y = 2\n")), reply(SUBMIT))
    result = run_assistant(str(repo), "add a module")
    assert (repo / "pkg" / "new.py").read_text() == "y = 2\n"
    assert result["diffs"][0]["is_new_file"] is True and result["diffs"][0]["added"] == 1


def test_assistant_endpoint_commits_only_its_own_files(client, sample_repo, scripted, llm):
    (sample_repo / "app" / "services" / "store.py").write_text("# the user's own uncommitted work\n")
    (sample_repo / "scratch.txt").write_text("untracked user file\n")

    h = register(client, "alice")
    repo_id = connect(client, sample_repo, h)
    scripted(reply(call("write_file", path="app/models.py", content=NEW_MODELS)), reply(SUBMIT))
    res = client.post(f"/api/repo/{repo_id}/assistant", json={"message": "validate"}, headers=h)
    data = res.json()
    assert res.status_code == 200, data

    assert data["files_changed"] == ["app/models.py"] and data["commit_sha"]
    assert data["diffs"][0]["added"] == 2 and data["quiz_error"] is None
    assert len(data["quizzes"]) == 3
    assert all(q["review"] is None and "correct_index" not in q and "explanation" not in q for q in data["quizzes"])

    committed = subprocess.run(["git", "show", "--name-only", "--format=%an|%s", "HEAD"], cwd=sample_repo, capture_output=True, text=True).stdout.split("\n")
    assert committed[0].startswith("CodeLiteracy|CodeLiteracy: Added validation.")
    assert [f for f in committed[1:] if f] == ["app/models.py"]  # not the user's other files
    status = subprocess.run(["git", "status", "--porcelain"], cwd=sample_repo, capture_output=True, text=True).stdout
    assert "store.py" in status and "scratch.txt" in status  # the user's work is still theirs, still uncommitted

    # the change's quizzes answer + credit the notebook as a bug-fix entry
    quiz = data["quizzes"][0]
    idx = next(i for i, o in enumerate(quiz["options"]) if o.startswith("right"))
    ans = client.post(f"/api/quiz/{quiz['id']}/answer", json={"selected_index": idx}, headers=h).json()
    assert ans["correct"] and ans["saved_to_notebook"]
    entry = client.get("/api/notebook", headers=h).json()[0]
    assert entry["category"] == "change" and entry["summary"].startswith("Added validation.") and entry["repo_name"] == "demo"
    assert entry["file_path"] == "app/models.py"


def test_quiz_failure_after_a_change_does_not_lose_the_change(client, sample_repo, scripted, llm):
    repo_id = connect(client, sample_repo)
    scripted(reply(call("write_file", path="app/models.py", content=NEW_MODELS)), reply(SUBMIT))
    llm.fail = "quota exhausted"
    data = client.post(f"/api/repo/{repo_id}/assistant", json={"message": "validate"}).json()
    assert data["files_changed"] == ["app/models.py"] and data["commit_sha"]  # change applied + committed
    assert data["quizzes"] == [] and "quota exhausted" in data["quiz_error"]

    llm.fail = None  # ...and the quiz can be retried later
    quizzes = client.post(f"/api/changes/{data['change_id']}/quizzes").json()
    assert len(quizzes) == 3
    again = client.post(f"/api/changes/{data['change_id']}/quizzes").json()
    assert [q["id"] for q in again] == [q["id"] for q in quizzes]  # existing ones, not regenerated
    assert client.post("/api/changes/nope/quizzes").status_code == 404


def test_assistant_endpoint_errors_are_clean(client, sample_repo, monkeypatch):
    repo_id = connect(client, sample_repo)
    assert client.post(f"/api/repo/{repo_id}/assistant", json={"message": "  "}).status_code == 400

    def boom(*a, **k):
        raise llm_client.LLMCallError("Gemini is overloaded right now.")

    monkeypatch.setattr(assistant_service, "generate_with_retry", boom)
    res = client.post(f"/api/repo/{repo_id}/assistant", json={"message": "fix"})
    assert res.status_code == 502 and "overloaded" in res.json()["detail"]


# ---- git ------------------------------------------------------------------------------------


def test_commit_changes_outside_a_git_repo_is_a_noop(tmp_path):
    (tmp_path / "a.py").write_text("x=1\n")
    assert commit_changes(str(tmp_path), "msg", ["a.py"]) is None
    assert commit_changes(str(tmp_path), "msg", []) is None


def test_commit_changes_skips_unchanged_files(sample_repo):
    assert commit_changes(str(sample_repo), "msg", ["app/models.py"]) is None


def test_commit_works_without_a_configured_git_identity(sample_repo, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(sample_repo / "nonexistent-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(sample_repo / "nonexistent-gitconfig"))
    (sample_repo / "app" / "models.py").write_text(NEW_MODELS)
    assert commit_changes(str(sample_repo), "msg", ["app/models.py"])


def test_clone_failure_never_leaks_the_token(monkeypatch):
    from git import GitCommandError

    from app.config import get_settings
    from app.services import github_service

    monkeypatch.setattr(get_settings(), "github_token", "ghp_SECRET123")

    def fail(url, *a, **k):
        raise GitCommandError(["git", "clone", url], 128, stderr=f"fatal: repository '{url}' not found")

    monkeypatch.setattr(github_service.Repo, "clone_from", fail)
    with pytest.raises(RepoConnectionError) as exc:
        connect_repository("https://github.com/x/y")
    text = str(exc.value)
    assert "ghp_SECRET123" not in text and "{exc}" not in text and "not found" in text


def test_only_https_and_ssh_urls_are_cloned():
    with pytest.raises(RepoConnectionError):
        connect_repository("http://github.com/x/y")  # plain http isn't a supported clone source
    with pytest.raises(RepoConnectionError):
        connect_repository("C:/definitely/not/here")


# ---- LLM client -----------------------------------------------------------------------------


class _Client:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.models = self

    def generate_content(self, **kwargs):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _api_error(code):
    return APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


def test_llm_retries_transient_errors_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm_client.time, "sleep", sleeps.append)
    c = _Client(_api_error(503), _api_error(503), "ok")
    assert llm_client.generate_with_retry(c, model="m") == "ok"
    assert c.calls == 3 and sleeps == [1.5, 4.0]


def test_llm_rate_limit_retries_once_then_gives_a_helpful_message(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    c = _Client(_api_error(429), _api_error(429))
    with pytest.raises(llm_client.LLMCallError, match="rate limit"):
        llm_client.generate_with_retry(c, model="m")
    assert c.calls == 2


def test_llm_does_not_retry_client_errors(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: pytest.fail("must not sleep"))
    c = _Client(_api_error(400))
    with pytest.raises(llm_client.LLMCallError, match="GEMINI_API_KEY"):
        llm_client.generate_with_retry(c, model="m")
    assert c.calls == 1


def test_json_object_retries_malformed_json_once(monkeypatch):
    outputs = iter(['{"a": ', '{"a": 1}'])
    monkeypatch.setattr(llm_client, "json_completion", lambda *a, **k: next(outputs))
    assert llm_client.json_object("s", "u") == {"a": 1}

    monkeypatch.setattr(llm_client, "json_completion", lambda *a, **k: "not json")
    with pytest.raises(llm_client.LLMCallError, match="malformed"):
        llm_client.json_object("s", "u")


def test_missing_api_key_is_reported(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    with pytest.raises(llm_client.LLMNotConfiguredError, match="GEMINI_API_KEY"):
        llm_client.require_api_key()


# ---- diffs / db migration / repo walking ------------------------------------------------------


def test_diff_line_numbers_context_and_gaps():
    before = "\n".join(f"line{i}" for i in range(1, 31)) + "\n"
    after = before.replace("line3\n", "LINE3\n").replace("line28\n", "LINE28\nextra\n")
    d = build_file_diff("f.py", before, after)
    assert (d["added"], d["removed"]) == (3, 2)
    kinds = [ln["kind"] for ln in d["lines"]]
    assert "gap" in kinds  # two far-apart hunks are separated, not one giant block
    deleted = [(ln["old_no"], ln["text"]) for ln in d["lines"] if ln["kind"] == "del"]
    assert deleted == [(3, "line3"), (28, "line28")]
    added = [(ln["new_no"], ln["text"]) for ln in d["lines"] if ln["kind"] == "add"]
    assert added == [(3, "LINE3"), (28, "LINE28"), (29, "extra")]
    assert build_file_diff("n.py", None, "a\nb\n")["is_new_file"] is True


def test_old_databases_get_new_columns_added(tmp_path, monkeypatch):
    """A database created by an older version (missing columns) is upgraded, not broken."""
    import sqlite3

    from sqlalchemy import create_engine, inspect

    from app import db as dbmod

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE repositories (id VARCHAR(32) PRIMARY KEY, source VARCHAR(500), name VARCHAR(200), local_path VARCHAR(1000), graph_json TEXT, connected_at DATETIME)")
    con.execute("CREATE TABLE notebook_entries (id VARCHAR(32) PRIMARY KEY, quiz_id VARCHAR(32), concept VARCHAR(200), question TEXT, summary TEXT, repo_name VARCHAR(200), created_at DATETIME)")
    con.execute("INSERT INTO notebook_entries VALUES ('n1', 'q1', 'c', 'q', 's', 'r', '2026-01-01')")
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    monkeypatch.setattr(dbmod, "engine", engine)
    dbmod.init_db()

    cols = {c["name"] for c in inspect(engine).get_columns("notebook_entries")}
    assert {"user_id", "category", "is_favorite", "user_notes", "file_path"} <= cols
    assert {"user_id", "onboarding_json", "flowchart_json", "file_details_json"} <= {c["name"] for c in inspect(engine).get_columns("repositories")}
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT concept, category, is_favorite FROM notebook_entries").one()
    assert row == ("c", "concept", 0)  # existing rows survive with sensible defaults
    dbmod.init_db()  # idempotent


def test_repo_walker_prunes_junk_and_own_workspace(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.services.dependency_graph import build_dependency_graph

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("import pkg.b\n")
    (tmp_path / "pkg" / "b.py").write_text("x = 1\n")
    for junk in ("node_modules/x", ".venv/lib", "__pycache__", "workspace/other-clone"):
        (tmp_path / junk).mkdir(parents=True)
        (tmp_path / junk / "junk.py").write_text("y = 1\n")

    monkeypatch.setattr(get_settings(), "workspace_dir", str(tmp_path / "workspace"))
    g = build_dependency_graph(str(tmp_path))
    assert sorted(n["id"] for n in g.nodes) == ["pkg/a.py", "pkg/b.py"]
    assert {"source": "pkg/a.py", "target": "pkg/b.py"} in g.edges

    # ...but a repo that is itself a clone *inside* the workspace is scanned normally
    g2 = build_dependency_graph(str(tmp_path / "workspace" / "other-clone"))
    assert [n["id"] for n in g2.nodes] == ["junk.py"]


def test_migration_relaxes_constraints_that_old_versions_made_required(tmp_path, monkeypatch):
    """The real upgrade path: an earlier version declared quizzes.change_id and
    notebook_entries.quiz_id NOT NULL. File-walkthrough quizzes and personal notes have neither, so
    adding columns alone isn't enough - the tables must be rebuilt, keeping their rows."""
    import sqlite3

    from sqlalchemy import create_engine, inspect, text

    from app import db as dbmod

    path = tmp_path / "v4.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE quizzes (id VARCHAR(32) NOT NULL, change_id VARCHAR(32) NOT NULL, concept VARCHAR(200) NOT NULL,
            question TEXT NOT NULL, options_json TEXT NOT NULL, correct_index INTEGER NOT NULL, created_at DATETIME NOT NULL,
            PRIMARY KEY (id));
        CREATE INDEX ix_quizzes_change_id ON quizzes (change_id);
        CREATE TABLE notebook_entries (id VARCHAR(32) NOT NULL, quiz_id VARCHAR(32) NOT NULL, concept VARCHAR(200) NOT NULL,
            question TEXT NOT NULL, summary TEXT NOT NULL, repo_name VARCHAR(200) NOT NULL, created_at DATETIME NOT NULL,
            PRIMARY KEY (id), UNIQUE (quiz_id));
        INSERT INTO quizzes VALUES ('q1','c1','Docstrings','What?','["a","b","c","d"]',1,'2026-01-01 00:00:00');
        INSERT INTO notebook_entries VALUES ('n1','q1','Docstrings','What?','sum','demo','2026-01-01 00:00:00');
        """
    )
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    monkeypatch.setattr(dbmod, "engine", engine)
    dbmod.init_db()

    nullable = {t: {c["name"]: c["nullable"] for c in inspect(engine).get_columns(t)} for t in ("quizzes", "notebook_entries")}
    assert nullable["quizzes"]["change_id"] and nullable["notebook_entries"]["quiz_id"]

    with engine.begin() as conn:
        # rows from the old version survived, with defaults filled in for the new columns
        assert conn.execute(text("SELECT id, change_id, concept, correct_index, repo_id, file_path FROM quizzes")).one() == ("q1", "c1", "Docstrings", 1, None, None)
        assert conn.execute(text("SELECT id, quiz_id, category, is_favorite FROM notebook_entries")).one() == ("n1", "q1", "concept", 0)
        # ...and the things the new features need are now possible
        conn.execute(text("INSERT INTO quizzes (id, concept, question, options_json, correct_index, created_at) VALUES ('q2','c','q','[]',0,'2026-01-02')"))
        conn.execute(text("INSERT INTO notebook_entries (id, concept, question, summary, repo_name, created_at, category, is_favorite) VALUES ('n2','My note','','text','Personal note','2026-01-02','note',0)"))
        conn.execute(text("INSERT INTO notebook_entries (id, concept, question, summary, repo_name, created_at, category, is_favorite) VALUES ('n3','Another','','text','Personal note','2026-01-02','note',0)"))  # two NULL quiz_ids is fine

    assert {i["name"] for i in inspect(engine).get_indexes("quizzes")} >= {"ix_quizzes_change_id", "ix_quizzes_repo_id", "ix_quizzes_user_id"}
    assert not [t for t in inspect(engine).get_table_names() if t.endswith("__old")]  # no leftovers
    dbmod.init_db()  # running it again changes nothing

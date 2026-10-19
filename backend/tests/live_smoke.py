"""End-to-end smoke test against a RUNNING server with a REAL Gemini key (uses free-tier quota).

    # terminal 1
    uvicorn app.main:app --port 8000
    # terminal 2
    .venv\\Scripts\\python tests\\live_smoke.py [http://localhost:8000]

Walks the whole learner journey as a guest: connect the sample project, onboarding, flowchart,
file walkthrough, wrong + right quiz answers, tutor chat, an AI-made code change with its diff,
the change's quiz, and the notebook. Exits non-zero if any step fails. The unit tests
(`pytest`) cover the same logic offline with a fake LLM; this checks the real wiring."""

import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
failures: list[str] = []


def step(name: str):
    print(f"\n== {name}")
    return time.time()


def check(cond: bool, msg: str) -> None:
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        failures.append(msg)


def call(method: str, path: str, token: str | None = None, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    res = requests.request(method, BASE + path, headers=headers, timeout=180, **kw)
    return res


t = step("health + guest login")
check(call("get", "/api/health").json()["status"] == "ok", "backend healthy")
auth = call("post", "/api/auth/guest").json()
token = auth["token"]
check(auth["user"]["is_guest"], f"guest account created ({auth['user']['username']})")

t = step("connect the CodeLiteracy sample (a safe copy)")
samples = call("get", "/api/repo/samples").json()
me = next(s for s in samples if s["id"] == "sample-codeliteracy")
conn = call("post", "/api/repo/connect", token, json={"source": me["source"]})
check(conn.status_code == 200, f"connected: {conn.json().get('node_count')} modules, {conn.json().get('edge_count')} deps")
repo_id = conn.json()["repo_id"]
check(me["source"] == "sample:codeliteracy", "sample is a per-connection disposable copy, not the live project")

t = step("onboarding (AI)")
ob = call("get", f"/api/repo/{repo_id}/onboarding", token).json()
check(not ob["degraded"], f"AI onboarding ok: {ob['main_idea'][:90]}...")
check(len(ob["tech_stack"]) > 0 and len(ob["folder_guide"]) > 0, f"{len(ob['tech_stack'])} technologies, {len(ob['folder_guide'])} folders")
check(len(ob["learning_curve"]["easy"]) > 0 and len(ob["learning_curve"]["hard"]) > 0, "easy AND hard concepts listed")

t = step("architecture flowchart (AI summaries + real edges)")
fc = call("get", f"/api/repo/{repo_id}/flowchart", token).json()
check(not fc["degraded"], f"{len(fc['nodes'])} nodes, {len(fc['edges'])} edges, tiers: {[t['id'] for t in fc['tiers']]}")
ids = {n["id"] for n in fc["nodes"]}
check(all(e["source"] in ids and e["target"] in ids for e in fc["edges"]), "every edge connects real nodes")
entry = next(n for n in fc["nodes"] if n["tier"] == "entrypoint")
print(f"     entrypoint: {entry['label']}: {entry['summary']}")

check(len(ob.get("learning_path", [])) >= 2, "reading order: " + " -> ".join(s["file_path"] for s in ob.get("learning_path", [])))

t = step("file browser")
files = call("get", f"/api/repo/{repo_id}/files", token).json()
check(len(files) > len(fc["nodes"]) - 5 and any(f["path"] == "README.md" for f in files), f"{len(files)} files can be opened")

t = step("file walkthrough + quiz")
target_file = "app/services/quiz_service.py"
fd = call("post", f"/api/repo/{repo_id}/file-details", token, json={"path": target_file}).json()
check(not fd["degraded"], f"walkthrough: {len(fd['line_sections'])} sections over {fd['total_lines']} lines")
check(all(1 <= s["start_line"] <= s["end_line"] <= fd["total_lines"] for s in fd["line_sections"]), "all line ranges are real")
check(3 <= len(fd["quizzes"]) <= 4, f"{len(fd['quizzes'])} quiz questions")
check(all("correct_index" not in q and q["review"] is None for q in fd["quizzes"]), "answers are not sent to the browser")
print("     overview:", fd["overview"])
print("     concepts:", [c["term"] for c in fd.get("key_concepts", [])])
print(f"     section 2: {fd['line_sections'][1]['title']} -> {fd['line_sections'][1]['explanation']}" if len(fd["line_sections"]) > 1 else "")
again = call("post", f"/api/repo/{repo_id}/file-details", token, json={"path": target_file}).json()
check([q["id"] for q in again["quizzes"]] == [q["id"] for q in fd["quizzes"]], "second open is cached (same quiz ids)")

t = step("explain selected lines")
sec = fd["line_sections"][min(1, len(fd["line_sections"]) - 1)]
ex = call("post", f"/api/repo/{repo_id}/explain-lines", token,
          json={"path": target_file, "start_line": sec["start_line"], "end_line": min(sec["end_line"], sec["start_line"] + 12)})
check(ex.status_code == 200 and len(ex.json().get("notes", [])) >= 1, f"{len(ex.json().get('notes', []))} line notes: {ex.json().get('summary', ex.text)[:110]}")


def answer(quiz, idx):
    return call("post", f"/api/quiz/{quiz['id']}/answer", token, json={"selected_index": idx}).json()


t = step("quiz: two tries, hint before the answer, notebook credit")
q1, q2 = fd["quizzes"][0], fd["quizzes"][1]
print("     Q:", q1["question"])
for i, o in enumerate(q1["options"]):
    print(f"       {chr(65 + i)}. {o}")
first = answer(q1, 0)
if first["correct"]:
    check(first["saved_to_notebook"], "correct on the first try -> credited to the notebook")
    first = answer(q2, 0)  # look for a wrong first try on the next question
    q1, q2 = q2, fd["quizzes"][2]
solved_one = False
if not first["correct"]:
    check(first["final"] is False and first["correct_index"] is None, "first wrong try keeps the answer hidden")
    print("     why that option is wrong:", first["option_feedback"])
    print("     hint:", first["hint"])
    check(bool(first["hint"]) or bool(first["option_feedback"]), "first wrong try teaches (hint / why it's wrong)")
    second = answer(q1, 1)
    check(second["final"] is True and second["correct_index"] is not None, f"second try closes the question (correct={second['correct']})")
    check(bool(second["explanation"]), "explanation shown once the question is closed")
    print("     explanation:", second["explanation"])
    if not second["correct"]:
        check(second["resource"] is not None and second["resource"]["url"].startswith("http"), f"two misses -> something to read: {second['resource']}")
    solved_one = second["correct"]

if not solved_one:  # make sure at least one correct answer reaches the notebook
    r = answer(q2, 0)
    if not r["correct"] and not r["final"]:
        r = answer(q2, 1)
nb_count = len(call("get", "/api/notebook", token).json())
print(f"     notebook entries so far: {nb_count}")

t = step("retry with a fresh question")
fresh = call("post", f"/api/quiz/{q1['id']}/retry", token).json()
check(fresh["id"] != q1["id"] and fresh["question"] != q1["question"], f"fresh question: {fresh['question'][:100]}")

t = step("tutor chat (general question, answered from the repo)")
chat = call("post", f"/api/repo/{repo_id}/chat", token, json={"message": "Where are quiz answers checked, and why on the server?"})
check(chat.status_code == 200 and len(chat.json()["reply"]) > 80, "tutor replied")
if chat.status_code == 200:
    print("     looked at:", chat.json()["sources"])
    print("     reply:", chat.json()["reply"][:700])
    check(any("quiz" in s for s in chat.json()["sources"]), "the tutor was shown the relevant file(s)")

t = step("tutor chat (quiz discussion)")
chat = call("post", f"/api/repo/{repo_id}/chat", token, json={
    "message": "Why is my choice incorrect?",
    "context": {"context_type": "quiz_discussion", "file_path": target_file, "question": q1["question"],
                "user_answer": q1["options"][0], "correct_answer": q1["options"][1]},
})
check(chat.status_code == 200 and len(chat.json()["reply"]) > 40, f"tutor replied: {chat.json().get('reply', chat.text)[:300]}...")
hist = call("get", f"/api/repo/{repo_id}/chat/history", token).json()
check(len(hist) == 4, "conversation persisted (2 questions + 2 replies)")

t = step("AI-assisted change: real diff + commit + quiz + undo")
ask = call("post", f"/api/repo/{repo_id}/assistant", token, json={
    "message": "In app/services/resource_service.py, add a one-line comment above the recommend_resource function explaining why we build the search URL ourselves instead of trusting an LLM-provided link."})
check(ask.status_code == 200, f"assistant finished ({ask.status_code}) {'' if ask.status_code == 200 else ask.text[:200]}")
if ask.status_code == 200:
    ch = ask.json()
    check(len(ch["files_changed"]) >= 1, f"changed: {ch['files_changed']}")
    check(len(ch["steps"]) >= 1 and all(s["explanation"] for s in ch["steps"]), f"{len(ch['steps'])} steps, each with a 'why'")
    d = ch["diffs"][0]
    check(d["added"] >= 1 and any(l["kind"] == "add" for l in d["lines"]), f"diff: +{d['added']} -{d['removed']} in {d['path']}")
    print("     work log:", [a["label"] for a in ch["activity"]])
    print("     summary:", ch["summary"])
    print("     concept:", ch["concept"], "-", ch["concept_explanation"])
    print("     verify:", ch["verify"])
    check(d["removed"] <= 2, "a small request made a small edit (the rest of the file is untouched)")
    check(ch["commit_sha"] is not None, f"committed as {str(ch['commit_sha'])[:7]}")
    check(3 <= len(ch["quizzes"]) <= 4 or bool(ch["quiz_error"]), f"{len(ch['quizzes'])} follow-up questions")
    history = call("get", f"/api/repo/{repo_id}/changes", token).json()
    check(len(history) == 1 and history[0]["can_undo"], "the change is in the history and can be undone")
    undo = call("post", f"/api/changes/{ch['change_id']}/undo", token)
    check(undo.status_code == 200 and undo.json()["restored"] == ch["files_changed"], "undo restored the file")

t = step("progress + notebook + stats")
print("     progress:", call("get", f"/api/repo/{repo_id}/progress", token).json())
nb = call("get", "/api/notebook", token).json()
check(len(nb) >= 1, f"{len(nb)} notebook entries: {[(e['category'], e['concept'][:30]) for e in nb]}")
check(all(e["repo_name"] == conn.json()["name"] for e in nb), "entries carry the real repo name")
if nb:
    call("post", f"/api/notebook/{nb[0]['id']}/favorite", token)
    check(len(call("get", "/api/notebook?favorites=true", token).json()) == 1, "favorites work")
stats = call("get", "/api/auth/me", token).json()["stats"]
check(stats["notebook_count"] == len(nb), f"stats: {stats}")

call("post", "/api/auth/logout", token)
check(call("get", "/api/auth/me", token).status_code == 401, "logout invalidates the token")

print("\n" + ("ALL LIVE CHECKS PASSED" if not failures else f"{len(failures)} FAILED:\n  - " + "\n  - ".join(failures)))
sys.exit(1 if failures else 0)

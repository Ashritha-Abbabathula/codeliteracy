# CodeLiteracy

An adaptive learning system for sustained developer comprehension in AI-assisted software
engineering. CodeLiteracy helps a developer understand an unfamiliar GitHub repository (Python
projects, in this version), then make AI-assisted changes to it, with every change explained in
plain language and followed by a short quiz, so understanding sticks instead of being outsourced
to the assistant.

Built against the SRS in `docs/SRS.md`.

## Start it

**Windows:** double-click `start.bat`. The first run sets everything up, then it opens the app
at http://localhost:5173.

**macOS / Linux:** `./start.sh`

You need Python 3.11+, Node.js, git, and a free Gemini API key
(https://aistudio.google.com/apikey) in `backend/.env` as `GEMINI_API_KEY=...`. Without a key the
app still opens and shows what it can read from the code itself (file structure, real imports,
docstrings); the AI explanations, tutor and quizzes need the key.

<details>
<summary>Manual setup</summary>

```bash
# backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # then fill in GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev
```

The frontend expects the backend at http://localhost:8000 (`frontend/.env` → `VITE_API_BASE_URL`).
</details>

## What you do in it

1. **Connect** a public GitHub URL or a local folder (or one of the one-click samples).
2. **Overview**: what the project is, its technologies, what's easy and hard in it, and a
   *reading order*: which files to read first, and why.
3. **Architecture map**: modules grouped into layers, with arrows that follow real imports.
4. **Read the code**: pick any file. You get a section-by-section walkthrough next to the code,
   a glossary of the ideas it uses, and a quiz. Select any lines to have exactly those lines
   explained, or ask the tutor about them.
5. **Make a change**: describe a fix or feature. The assistant makes it, shows the exact diff,
   its work log, the idea behind it, what and why step by step, how to check it, then quizzes
   you. Every change is a git commit and can be undone from the app.
6. **Tutor chat** (bottom right, any time): answers from the repository's actual files and shows
   which files it looked at.
7. **Notebook**: every question you answer correctly is saved, with your own notes.

### How the quizzes teach

You get two tries per question. A first wrong answer doesn't reveal the answer: you're told why
*that option* is wrong and given a hint. After a second miss you see the answer, the explanation
and something to read, and can ask for a fresh question on the same concept. Answers are checked
on the server, and only a genuinely correct answer reaches the notebook.

## How it maps to the SRS

| Requirement | Where |
|---|---|
| FR1 connect a repo | `services/github_service.py`, `routers/repo.py` |
| FR2 dependency graph | `services/dependency_graph.py` |
| FR3 flowchart | `services/flowchart_service.py`, `components/ArchitectureFlowchart.tsx` |
| FR4 plain-language explanations | `services/onboarding_service.py`, `services/code_explainer_service.py` |
| FR5–FR7 assistant that explains itself | `services/assistant_service.py`, `routers/assistant.py`, `components/ErrorFixer.tsx` |
| FR8 quiz after a change / a file | `services/quiz_service.py` |
| FR9 resource on a wrong answer, FR10 retake | `routers/quiz.py` |
| FR11–FR12 notebook | `routers/notebook.py`, `pages/Notebook.tsx` |
| Reliability (stays accurate as the repo changes) | caches keyed by file content; graph rebuilt and flowchart dropped after every change/undo |
| Security | per-user isolation (`deps.py`); the assistant can only read/write inside the connected repo and never runs commands |

## Architecture

- **`backend/`**: FastAPI + SQLAlchemy (SQLite). Clones/parses repos, talks to the Gemini API,
  stores users, quizzes, changes, chat and notebook entries.
  - `services/repo_context.py` is what keeps the AI honest: the file list, AST outlines and the
    files relevant to a question are read off disk and put in front of the model.
  - If the AI is unavailable, features fall back to facts from the code (and say so) or return a
    clear error. Nothing is ever replaced by canned text that pretends to be about your code.
- **`frontend/`**: React + TypeScript (Vite), no UI framework.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest                 # 67 tests, offline (a scripted fake stands in for Gemini)
python tests/live_smoke.py       # end-to-end against a running server with your real key
```

`live_smoke.py` prints what the AI actually said at each step, which is the quickest way to
judge answer quality after changing a prompt.

## Scope

Per the SRS's design constraints this version targets one ecosystem: Python repositories,
analyzed with `ast`. Other languages, team features and unexplained autonomous changes are out
of scope. The assistant edits files but does not run shell commands (see the note at the top of
`services/assistant_service.py`).

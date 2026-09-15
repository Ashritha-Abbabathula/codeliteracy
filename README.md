# CodeLiteracy

An adaptive learning system for sustained developer comprehension in AI-assisted software
engineering. CodeLiteracy helps a developer understand an unfamiliar GitHub repository (Python
projects, in this initial version), then make AI-assisted changes to it — with every change
explained in plain language and followed by a short quiz, so understanding actually sticks instead
of being outsourced to the assistant.

Built against the SRS in `docs/SRS.md`, sprint by sprint (see git history — each sprint is its own
commit, matching the SRS's preliminary schedule).

## Architecture

- **`backend/`** — FastAPI + SQLAlchemy (SQLite). Clones/parses repos, talks to the Gemini API
  (free tier) for explanations/assistant/quiz generation, stores notebook entries.
- **`frontend/`** — React + TypeScript (Vite). Chat interface, dependency-graph viewer, quiz panel,
  notebook view.

## Modules (built one per sprint)

| Sprint | Weeks | Module | Covers |
|---|---|---|---|
| 1 | 1–2 | Repo analyzer (graph) | FR1, FR2 |
| 2 | 3–4 | Repo analyzer (flowchart + explanations) | FR3, FR4 |
| 3 | 5–6 | AI coding assistant | FR5, FR6, FR7 |
| 4 | 7–8 | Quiz engine | FR8 |
| 5 | 9–10 | Resource recommendation & retry | FR9, FR10 |
| 6 | 11–12 | Learning notebook | FR11, FR12 |

## Setup

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env   # then fill in GEMINI_API_KEY (free: https://aistudio.google.com/apikey)
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. The frontend expects the backend at http://localhost:8000
(configurable via `frontend/.env` → `VITE_API_BASE_URL`).

## Scope note

Per the SRS's design constraints, this initial version targets a **single language/ecosystem**:
Python repositories, analyzed via `ast`-based import parsing. Multi-repo/team features, other
languages, and fully autonomous (unexplained) changes are explicitly out of scope for v1.

"""Conversational onboarding for a freshly connected repo: main idea, tech stack, what's
easy vs. hard to learn, and a folder-by-folder guide.

Grounded in real evidence gathered from the repo (README, dependency manifests, file
tree). If the AI is unavailable, `degraded_onboarding` builds the same shape from that
evidence alone and says plainly that it's not an AI summary - it never invents a
description of what the project "coordinates" or "processes"."""

import json
import re
from pathlib import Path
from typing import Any

from app.services.llm_client import LLMCallError, LLMNotConfiguredError, json_object
from app.services.repo_context import python_outline, rank_by_degree
from app.services.repo_utils import iter_files

_ONBOARDING_SYSTEM_PROMPT = """\
You are CodeLiteracy's interactive repository onboarding tutor. A developer has just \
connected a repository they want to learn. Welcome them and give a clear, honest, friendly \
breakdown of the project, based ONLY on the evidence provided (README, dependency manifests, \
file tree). If something isn't evident, say less rather than guess.

Respond with strict JSON only matching this schema:
{
  "greeting": "One warm sentence, e.g. 'Hello! I'll explain what this project is about briefly and how it fits together.'",
  "main_idea": "2-3 plain-language sentences: what the project is for and what problem it solves.",
  "tech_stack": [{"name": "FastAPI", "category": "Backend", "purpose": "Serves the REST API"}],
  "learning_curve": {
    "easy": ["2-3 beginner-friendly parts of THIS codebase, named specifically"],
    "hard": ["2-3 harder or subtler parts of THIS codebase, named specifically, with why"]
  },
  "folder_guide": [
    {"folder": "backend/app/routers", "title": "API routes",
     "purpose": "what lives here and why", "key_files": ["repo.py"]}
  ],
  "learning_path": [
    {"file_path": "app/models.py", "title": "Start with the data",
     "why": "one sentence: what the learner will understand after reading this file, and why it comes at this point"}
  ],
  "transition_message": "One short sentence saying you're about to show the architecture flowchart."
}

main_idea: say what a user of the project can DO with it, in words a newcomer would use; \
prefer what the code outlines show over marketing language in the README.
tech_stack: only technologies visible in the manifests/imports (max 10); purpose says what it \
is used for in THIS project.
learning_curve: name real files or functions from the outlines, and say in a few words what \
makes each one easy or hard.
folder_guide: the most important 4-8 folders that exist in the tree.
learning_path: the 4-6 files a newcomer should read, in the order that builds understanding \
(usually: the simplest foundations other files depend on first, then the core logic, then the \
entry point that ties them together). Use only exact paths from "Candidate files to read". \
Do not wrap the JSON in markdown fences."""

_CATEGORIES = {
    "fastapi": "Web framework", "flask": "Web framework", "django": "Web framework",
    "starlette": "Web framework", "express": "Web framework", "uvicorn": "Server",
    "gunicorn": "Server", "sqlalchemy": "Database", "psycopg2": "Database",
    "pymongo": "Database", "redis": "Cache/Queue", "celery": "Task queue",
    "pydantic": "Validation", "pytest": "Testing", "requests": "HTTP client",
    "httpx": "HTTP client", "aiohttp": "HTTP client", "numpy": "Data/ML", "pandas": "Data/ML",
    "torch": "Data/ML", "tensorflow": "Data/ML", "scikit-learn": "Data/ML",
    "react": "Frontend", "vue": "Frontend", "vite": "Build tool", "typescript": "Language",
    "anthropic": "AI", "openai": "AI", "google-genai": "AI", "networkx": "Graphs",
    "gitpython": "Git", "click": "CLI", "typer": "CLI", "tensorboard": "Data/ML",
}

_TREE_SAMPLE = 60


def _manifest_dependencies(repo_path: Path) -> list[str]:
    """Real dependency names from requirements*.txt / pyproject.toml / package.json."""
    names: list[str] = []
    for path in iter_files(repo_path):
        if len(path.relative_to(repo_path.resolve()).parts) > 3:
            continue
        try:
            if path.name.startswith("requirements") and path.suffix == ".txt":
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    m = re.match(r"^\s*([A-Za-z0-9_.\-]+)", line)
                    if m and not line.lstrip().startswith(("#", "-")):
                        names.append(m.group(1))
            elif path.name == "pyproject.toml":
                text = path.read_text(encoding="utf-8", errors="ignore")
                block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
                if block:
                    names += re.findall(r'"\s*([A-Za-z0-9_.\-]+)', block.group(1))
            elif path.name == "package.json":
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                names += list((data.get("dependencies") or {}).keys())
        except (OSError, ValueError):
            continue
    seen: set[str] = set()
    ordered = []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(n)
    return ordered


_ENTRY_STEMS = {"main", "app", "server", "run", "cli", "manage", "__main__", "train", "start"}


def _path_candidates(root: Path, files: list[str], graph: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Python files worth reading first, each with facts a path can be built from: how many
    files import it, how many it imports, and its outline."""
    python = [f for f in files if f.endswith(".py") and not f.endswith("__init__.py")
              and not any(part in ("tests", "test", "docs", "examples", "migrations") for part in f.split("/")[:-1])
              and not Path(f).name.startswith("test_")]
    imported_by: dict[str, int] = {}
    imports: dict[str, int] = {}
    for edge in (graph or {}).get("edges", []):
        imported_by[edge["target"]] = imported_by.get(edge["target"], 0) + 1
        imports[edge["source"]] = imports.get(edge["source"], 0) + 1
    order = [p for p in rank_by_degree(graph) if p in set(python)] + sorted(python)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for rel in order:
        if rel in seen:
            continue
        seen.add(rel)
        try:
            source = (root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not source.strip():
            continue
        out.append({
            "path": rel, "lines": len(source.splitlines()),
            "imported_by": imported_by.get(rel, 0), "imports": imports.get(rel, 0),
            "outline": python_outline(source, max_items=8),
        })
        if len(out) >= 14:
            break
    return out


def fallback_learning_path(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    """A reading order from the dependency graph alone: files that others build on and that
    depend on little themselves come first (you can read them without knowing anything else),
    entry points last (they only make sense once you know what they wire together)."""
    def is_entry(c: dict[str, Any]) -> bool:
        return Path(c["path"]).stem.lower() in _ENTRY_STEMS

    core = sorted((c for c in candidates if not is_entry(c)),
                  key=lambda c: (c["imports"], -c["imported_by"], c["lines"]))[:4]
    entries = sorted((c for c in candidates if is_entry(c)), key=lambda c: -c["imports"])[:1]
    path = []
    for c in core + entries:
        doc = next((o.strip('"') for o in c["outline"] if o.startswith('"""')), "")
        if is_entry(c):
            why = "An entry point: it wires the pieces above together, so read it once you know them."
        elif c["imported_by"]:
            why = f"{c['imported_by']} other file(s) import this, and it depends on {c['imports'] or 'no'} other file(s) here, so it's a good foundation."
        else:
            why = f"A self-contained file ({c['lines']} lines) you can read on its own."
        if doc:
            why = f"{doc.rstrip('.')}. {why}"
        path.append({"file_path": c["path"], "title": Path(c["path"]).name, "why": why[:400]})
    return path


def _clean_learning_path(raw: Any, candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only steps that point at files that really exist (models misremember paths)."""
    known = {c["path"] for c in candidates}
    by_name: dict[str, list[str]] = {}
    for path in known:
        by_name.setdefault(Path(path).name, []).append(path)
    steps: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("file_path") or "").strip().lstrip("./")
        if path not in known:
            same_name = by_name.get(Path(path).name, [])
            if len(same_name) != 1:
                continue
            path = same_name[0]
        if any(s["file_path"] == path for s in steps):
            continue
        why = str(item.get("why") or "").strip()
        if why:
            steps.append({"file_path": path, "title": str(item.get("title") or Path(path).name).strip()[:80], "why": why[:400]})
    return steps[:6]


def _gather_repo_context(repo_path: Path, graph: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    root = repo_path.resolve()
    files = [p.relative_to(root).as_posix() for p in iter_files(root)]
    top_dirs: dict[str, int] = {}
    for f in files:
        parts = f.split("/")
        if len(parts) > 1:
            top_dirs[parts[0]] = top_dirs.get(parts[0], 0) + 1
    deps = _manifest_dependencies(root)

    readme_text = ""
    for candidate in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
        if (root / candidate).is_file():
            readme_text = (root / candidate).read_text(encoding="utf-8", errors="ignore")[:3500]
            break

    parts = [
        f"Repository name: {root.name}",
        f"Total files: {len(files)} ({sum(1 for f in files if f.endswith('.py'))} Python)",
        "Top-level folders (file count): "
        + (", ".join(f"{d} ({n})" for d, n in sorted(top_dirs.items())) or "(none - flat layout)"),
        "Declared dependencies: " + (", ".join(deps[:40]) or "(none found)"),
        "File tree sample:\n" + "\n".join(files[:_TREE_SAMPLE]),
    ]
    candidates = _path_candidates(root, files, graph)
    if candidates:
        blocks = []
        for c in candidates:
            head = f"## {c['path']} ({c['lines']} lines; imported by {c['imported_by']} file(s), imports {c['imports']})"
            blocks.append(head + ("\n" + "\n".join(c["outline"]) if c["outline"] else ""))
        parts.append("Candidate files to read (outlines taken from the real code):\n\n" + "\n\n".join(blocks))
    if readme_text:
        parts.append(f"--- README ---\n{readme_text}")
    facts = {"name": root.name, "files": files, "top_dirs": top_dirs, "deps": deps, "readme": readme_text,
             "candidates": candidates}
    return "\n\n".join(parts), facts


def _readme_summary(readme: str) -> str | None:
    """First real paragraph of a README (skipping title lines, badges and images)."""
    for block in re.split(r"\n\s*\n", readme):
        text = " ".join(
            line.strip() for line in block.splitlines()
            if line.strip() and not line.strip().startswith(("#", "![", "[![", "<", "```", "="))
        )
        if len(text) > 40:
            return text[:400]
    return None


def degraded_onboarding(facts: dict[str, Any], reason: str) -> dict[str, Any]:
    """The same shape as the AI result, built only from facts read off disk."""
    tech = []
    for dep in facts["deps"]:
        category = _CATEGORIES.get(dep.lower())
        if category:
            tech.append({"name": dep, "category": category, "purpose": "Declared dependency"})
    if any(f.endswith(".py") for f in facts["files"]):
        tech.insert(0, {"name": "Python", "category": "Language", "purpose": "Primary language of this repository"})

    folder_guide = []
    for folder, count in sorted(facts["top_dirs"].items(), key=lambda kv: -kv[1])[:8]:
        key_files = [f.split("/")[-1] for f in facts["files"] if f.startswith(folder + "/")][:4]
        folder_guide.append({
            "folder": folder, "title": folder, "key_files": key_files,
            "purpose": f"Contains {count} file(s).",
        })

    name = facts["name"]
    return {
        "greeting": f"Hello! Here's what I can tell you about {name}.",
        "main_idea": _readme_summary(facts["readme"]) or f"{name} has no README, so there is no author-written description to show.",
        "tech_stack": tech,
        "learning_curve": {"easy": [], "hard": []},
        "folder_guide": folder_guide,
        "learning_path": fallback_learning_path(facts.get("candidates", [])),
        "transition_message": "Let's look at the architecture flowchart.",
        "degraded": True,
        "notice": f"AI summary unavailable: {reason} Showing facts read directly from the repository instead.",
    }


def learning_path_for(repo_path: str, graph: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """The graph-derived reading order (no AI) - used for onboarding results cached before
    learning paths existed."""
    root = Path(repo_path).resolve()
    files = [p.relative_to(root).as_posix() for p in iter_files(root)]
    return fallback_learning_path(_path_candidates(root, files, graph))


def generate_repo_onboarding(repo_path: str, graph: dict[str, Any] | None = None) -> dict[str, Any]:
    context, facts = _gather_repo_context(Path(repo_path), graph)

    try:
        parsed = json_object(
            _ONBOARDING_SYSTEM_PROMPT,
            f"Analyze this repository and produce the onboarding breakdown:\n\n{context}",
            max_tokens=4500,
        )
    except (LLMNotConfiguredError, LLMCallError) as exc:
        return degraded_onboarding(facts, str(exc))

    lc = parsed.get("learning_curve") if isinstance(parsed.get("learning_curve"), dict) else {}
    result = {
        "greeting": str(parsed.get("greeting") or f"Hello! I'll explain what {facts['name']} is about and how it fits together."),
        "main_idea": str(parsed.get("main_idea") or "").strip(),
        "tech_stack": [t for t in (parsed.get("tech_stack") or []) if isinstance(t, dict) and t.get("name")][:12],
        "learning_curve": {
            "easy": [str(x) for x in (lc.get("easy") or [])][:5],
            "hard": [str(x) for x in (lc.get("hard") or [])][:5],
        },
        "folder_guide": [f for f in (parsed.get("folder_guide") or []) if isinstance(f, dict) and f.get("folder")][:10],
        "learning_path": _clean_learning_path(parsed.get("learning_path"), facts["candidates"])
                         or fallback_learning_path(facts["candidates"]),
        "transition_message": str(parsed.get("transition_message") or "Let's look at the architecture flowchart."),
        "degraded": False,
        "notice": None,
    }
    for t in result["tech_stack"]:
        t.setdefault("category", "Library")
        t.setdefault("purpose", "")
    for f in result["folder_guide"]:
        f.setdefault("title", f["folder"])
        f.setdefault("purpose", "")
        f["key_files"] = [str(k) for k in (f.get("key_files") or [])][:6]
    if not result["main_idea"]:
        return degraded_onboarding(facts, "The AI returned an incomplete summary.")
    return result

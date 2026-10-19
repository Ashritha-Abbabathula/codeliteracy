"""A clean, layered architecture flowchart (Entrypoint -> Routes -> Logic -> Data ->
External) instead of a raw file-by-file import web.

Everything structural is derived from the code itself: tiers from directory names,
decorators and imports; edges from *real* import statements between the chosen modules
(labelled with the names actually imported); external nodes from third-party libraries the
code really imports. The AI only writes the one-sentence role summaries, and if it's
unavailable those fall back to each module's own docstring / defined symbols."""

import ast
import re
import sys
from pathlib import Path
from typing import Any

from app.services.dependency_graph import (
    ParsedModule,
    _discover_modules,
    _package_of,
    _resolve,
    build_dependency_graph,
)
from app.services.llm_client import LLMCallError, LLMNotConfiguredError, json_object

TIER_ORDER = ["entrypoint", "router", "service", "model", "external"]
TIER_COLORS = {
    "entrypoint": "#3b82f6", "router": "#8b5cf6", "service": "#10b981",
    "model": "#f59e0b", "external": "#e11d48",
}
TIER_LABELS = {
    "entrypoint": "Entrypoint", "router": "API & Routing", "service": "Core Logic",
    "model": "Data & Models", "external": "External Service / Library",
}
TIER_INFO = [
    {"id": "entrypoint", "title": "1. Entrypoints & Scripts", "description": "Where execution starts"},
    {"id": "router", "title": "2. API & Routing", "description": "Endpoints and request handling"},
    {"id": "service", "title": "3. Core Logic & Services", "description": "The main operations and algorithms"},
    {"id": "model", "title": "4. Data, Models & Config", "description": "State, schemas and persistence"},
    {"id": "external", "title": "5. External Services & Libraries", "description": "Third-party systems this code talks to"},
]
MAX_PER_TIER = {"entrypoint": 4, "router": 5, "service": 6, "model": 5, "external": 5}

_ENTRY_STEMS = {"main", "app", "server", "run", "cli", "manage", "wsgi", "asgi", "__main__",
                "train", "sample", "bench", "serve", "inference", "start"}
_ROUTER_DIRS = {"routers", "router", "routes", "views", "controllers", "endpoints", "api", "handlers", "resources"}
_MODEL_NAMES = {"models", "model", "schemas", "schema", "entities", "db", "database", "orm", "config", "configs", "settings"}
_ROUTER_CODE = re.compile(r"APIRouter\(|Blueprint\(|@\w+\.(?:get|post|put|patch|delete|route)\(")
_SKIP_STEMS = {"conftest", "setup", "__init__"}
# Frameworks and utilities are how the app is *built*, not external systems it talks to.
_NOT_EXTERNAL = {"fastapi", "flask", "django", "starlette", "pydantic", "pydantic_settings", "uvicorn",
                 "pytest", "typing_extensions", "dotenv", "networkx", "setuptools", "click", "typer"}

# Well-known third-party libraries -> (display name, what it's for)
_EXTERNALS = {
    "sqlalchemy": ("SQLAlchemy", "Relational database access"),
    "sqlite3": ("SQLite", "Embedded SQL database"),
    "psycopg2": ("PostgreSQL", "PostgreSQL database driver"),
    "pymongo": ("MongoDB", "MongoDB database driver"),
    "redis": ("Redis", "Cache / message broker"),
    "requests": ("HTTP APIs (requests)", "Outbound HTTP calls"),
    "httpx": ("HTTP APIs (httpx)", "Outbound HTTP calls"),
    "aiohttp": ("HTTP APIs (aiohttp)", "Outbound HTTP calls"),
    "google": ("Google / Gemini API", "Google cloud & AI services"),
    "anthropic": ("Anthropic API", "Claude language models"),
    "openai": ("OpenAI API", "OpenAI language models"),
    "git": ("Git (GitPython)", "Git repository operations"),
    "boto3": ("AWS (boto3)", "Amazon Web Services"),
    "torch": ("PyTorch", "Deep-learning framework"),
    "tensorflow": ("TensorFlow", "Deep-learning framework"),
    "numpy": ("NumPy", "Numerical computing"),
    "pandas": ("pandas", "Data analysis"),
    "transformers": ("Hugging Face Transformers", "Pretrained ML models"),
    "datasets": ("Hugging Face Datasets", "ML datasets"),
    "tiktoken": ("tiktoken", "Tokenization"),
    "celery": ("Celery", "Background task queue"),
    "kafka": ("Kafka", "Event streaming"),
    "stripe": ("Stripe", "Payments API"),
}


class _Info:
    """What we learn from parsing one module once."""

    def __init__(self, module: ParsedModule, source: str):
        self.module = module
        self.path = module.rel_path
        self.source = source
        try:
            self.tree: ast.Module | None = ast.parse(source)
        except SyntaxError:
            self.tree = None
        self.docstring = ast.get_docstring(self.tree).strip().splitlines()[0] if self.tree and ast.get_docstring(self.tree) else None
        self.symbols = self._symbols()
        self.top_imports = self._top_level_imports()
        self.has_main_guard = bool(re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", source))

    def _symbols(self) -> list[str]:
        out: list[str] = []
        if self.tree:
            for node in self.tree.body:
                if isinstance(node, ast.ClassDef):
                    out.append(f"class {node.name}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                    out.append(f"{node.name}()")
        return out[:4]

    def _top_level_imports(self) -> set[str]:
        names: set[str] = set()
        if self.tree:
            for node in ast.walk(self.tree):
                if isinstance(node, ast.Import):
                    names.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.add(node.module.split(".")[0])
        return names


def _classify(info: _Info) -> str:
    parts = [p.lower() for p in Path(info.path).parts]
    stem = Path(info.path).stem.lower()
    dirs = set(parts[:-1])

    if dirs & _ROUTER_DIRS or stem in _ROUTER_DIRS:
        return "router"
    # Entrypoint before decorator-sniffing: main.py routinely has an @app.get("/health")
    # route of its own but is still the file that boots and wires up the application.
    if stem in _ENTRY_STEMS or info.has_main_guard:
        return "entrypoint"
    if _ROUTER_CODE.search(info.source):
        return "router"
    if stem in _MODEL_NAMES or dirs & _MODEL_NAMES:
        return "model"
    return "service"


def _is_noise(path: str) -> bool:
    parts = [p.lower() for p in Path(path).parts]
    stem = Path(path).stem.lower()
    return (
        stem in _SKIP_STEMS
        or stem.startswith("test_") or stem.endswith("_test")
        or bool({"tests", "test", "docs", "examples", "migrations", "scripts", "benchmarks"} & set(parts[:-1]))
    )


def _import_names(info: _Info, dotted_to_rel: dict[str, str]) -> dict[str, list[str]]:
    """target module path -> the names this module actually imports from it."""
    result: dict[str, set[str]] = {}
    if not info.tree:
        return {}
    for node in ast.walk(info.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve(alias.name, dotted_to_rel)
                if target and target != info.path:
                    result.setdefault(target, set()).add(alias.asname or alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                package = _package_of(info.module)
                up = node.level - 1
                base_parts = package[: len(package) - up] if up <= len(package) else []
                base = ".".join(base_parts)
                base = f"{base}.{node.module}" if base and node.module else (node.module or base)
            else:
                base = node.module
            for alias in node.names:
                if alias.name == "*":
                    continue
                sub = _resolve(f"{base}.{alias.name}" if base else alias.name, dotted_to_rel)
                target = sub if sub and sub != info.path else (_resolve(base, dotted_to_rel) if base else None)
                if target and target != info.path:
                    result.setdefault(target, set()).add(alias.name)
    return {t: sorted(n) for t, n in result.items()}


def _local_top_levels(modules: list[ParsedModule]) -> set[str]:
    return {m.dotted.split(".")[0] for m in modules}


def _fallback_summary(info: _Info) -> str:
    if info.docstring:
        return info.docstring
    if info.symbols:
        return "Defines " + ", ".join(info.symbols) + "."
    return "No docstring or top-level definitions to summarize."


_SUMMARY_PROMPT = """\
You are documenting a codebase's architecture. For each module below write ONE plain-language \
sentence (max 25 words) saying what role it plays, based only on the code shown. Respond with \
strict JSON only: {"summaries": {"<path>": "<sentence>"}}. Use the exact paths given."""


def _ai_summaries(infos: list[_Info]) -> dict[str, str]:
    blocks = []
    for info in infos:
        head = "\n".join(info.source.splitlines()[:40])[:1200]
        blocks.append(f"### {info.path}\n{head}")
    parsed = json_object(_SUMMARY_PROMPT, "\n\n".join(blocks), max_tokens=2500)
    raw = parsed.get("summaries")
    if not isinstance(raw, dict):
        return {}
    return {k: v.strip() for k, v in raw.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}


def generate_architecture_flowchart(repo_path_str: str) -> dict[str, Any]:
    root = Path(repo_path_str).resolve()
    graph = build_dependency_graph(str(root))
    modules = {m.rel_path: m for m in _discover_modules(root)}
    dotted_to_rel = {m.dotted: m.rel_path for m in modules.values()}

    infos: dict[str, _Info] = {}
    for rel, module in modules.items():
        if _is_noise(rel):
            continue
        try:
            infos[rel] = _Info(module, (root / rel).read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue

    degree: dict[str, int] = {p: 0 for p in infos}
    for edge in graph.edges:
        for end in (edge["source"], edge["target"]):
            if end in degree:
                degree[end] += 1

    tiers = {p: _classify(i) for p, i in infos.items()}

    # Pick the most connected modules per tier (ties: shallower path first).
    selected: dict[str, list[str]] = {t: [] for t in TIER_ORDER}
    for tier in ("entrypoint", "router", "service", "model"):
        ranked = sorted((p for p in infos if tiers[p] == tier),
                        key=lambda p: (-degree[p], len(Path(p).parts), p))
        selected[tier] = ranked[:MAX_PER_TIER[tier]]
    chosen = [p for t in TIER_ORDER for p in selected[t]]
    chosen_set = set(chosen)

    # External libraries actually imported (third-party only).
    stdlib = set(sys.stdlib_module_names) - {"sqlite3"}
    local = _local_top_levels(list(modules.values()))
    usage: dict[str, set[str]] = {}
    for path, info in infos.items():
        for name in info.top_imports:
            if name in stdlib or name in local or name.startswith("_"):
                continue
            usage.setdefault(name, set()).add(path)
    usage = {n: u for n, u in usage.items() if n not in _NOT_EXTERNAL}
    known = sorted((n for n in usage if n in _EXTERNALS), key=lambda n: (-len(usage[n]), n))
    # Unknown libraries only make the picture if several files depend on them.
    unknown = sorted((n for n in usage if n not in _EXTERNALS and len(usage[n]) >= 3),
                     key=lambda n: (-len(usage[n]), n))
    external_names = (known + unknown)[: MAX_PER_TIER["external"]]

    # Role summaries: AI if available, else each module's own docstring/symbols.
    summaries: dict[str, str] = {}
    degraded = False
    notice = None
    try:
        summaries = _ai_summaries([infos[p] for p in chosen])
    except (LLMNotConfiguredError, LLMCallError) as exc:
        degraded = True
        notice = f"AI role summaries unavailable: {exc} Showing each module's own docstring instead."

    def label_for(path: str) -> str:
        name = Path(path).name
        clash = sum(1 for p in chosen if Path(p).name == name) > 1
        return "/".join(Path(path).parts[-2:]) if clash else name

    def node_id(path: str) -> str:
        return f"node-{path}"

    imports_of: dict[str, list[str]] = {}
    imported_by: dict[str, list[str]] = {}
    for edge in graph.edges:
        imports_of.setdefault(edge["source"], []).append(edge["target"])
        imported_by.setdefault(edge["target"], []).append(edge["source"])

    nodes: list[dict[str, Any]] = []
    for tier in TIER_ORDER:
        if tier == "external":
            for name in external_names:
                display, purpose = _EXTERNALS.get(name, (name, "Third-party library"))
                users = sorted(usage[name])
                nodes.append({
                    "id": f"ext-{name}", "label": display, "tier": "external",
                    "tier_label": TIER_LABELS["external"],
                    "summary": f"{purpose}. Imported by {len(users)} file(s): {', '.join(Path(u).name for u in users[:4])}"
                               + ("…" if len(users) > 4 else "."),
                    "file_path": "", "key_functions": [], "badge_color": TIER_COLORS["external"],
                    "imports": [], "imported_by": [Path(u).name for u in users[:8]],
                })
            continue
        for path in selected[tier]:
            info = infos[path]
            nodes.append({
                "id": node_id(path), "label": label_for(path), "tier": tier,
                "tier_label": TIER_LABELS[tier],
                "summary": summaries.get(path) or _fallback_summary(info),
                "file_path": path, "key_functions": info.symbols or [],
                "badge_color": TIER_COLORS[tier],
                "imports": [Path(t).name for t in imports_of.get(path, [])][:8],
                "imported_by": [Path(s).name for s in imported_by.get(path, [])][:8],
            })

    # Edges: real imports between chosen modules, flowing "down" the tiers (an import that
    # points back up a tier would only add cross-cutting lines to what should be a clean
    # picture; it is still listed in each node's imports/imported_by).
    tier_rank = {t: i for i, t in enumerate(TIER_ORDER)}
    edges: list[dict[str, Any]] = []
    for path in chosen:
        for target, names in _import_names(infos[path], dotted_to_rel).items():
            if target not in chosen_set or tier_rank[tiers[target]] < tier_rank[tiers[path]]:
                continue
            shown = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
            edges.append({
                "id": f"e-{path}->{target}", "source": node_id(path), "target": node_id(target),
                "label": f"imports {shown}" if shown else "imports",
            })
    for name in external_names:
        for path in sorted(usage[name] & chosen_set):
            edges.append({
                "id": f"e-{path}->ext-{name}", "source": node_id(path), "target": f"ext-{name}",
                "label": "uses",
            })

    present = {n["tier"] for n in nodes}
    return {
        "nodes": nodes,
        "edges": edges,
        "tiers": [t for t in TIER_INFO if t["id"] in present],
        "degraded": degraded,
        "notice": notice,
        "total_modules": len(infos),
        "shown_modules": len(chosen),
    }

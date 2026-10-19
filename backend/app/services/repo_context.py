"""Grounding for the AI: what is actually in the repository.

The tutor, onboarding and learning path are only as good as what they are shown. Everything
here is read straight off disk (file list, AST outlines, README, the files most relevant to a
question), so the model answers from the learner's real code instead of from the repo's name."""

import ast
import re
from pathlib import Path
from typing import Any

from app.services.repo_utils import iter_files

TEXT_SUFFIXES = {
    ".py", ".md", ".rst", ".txt", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml",
    ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".sh", ".sql", ".env.example",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile", "LICENSE", ".gitignore", "requirements.txt"}
MAX_LISTED_FILES = 800
MAX_FILE_BYTES = 400_000
_LOCKFILES = {"package-lock.json", "yarn.lock", "poetry.lock", "pnpm-lock.yaml", "uv.lock"}

_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "was", "one", "our", "out", "use",
    "how", "why", "what", "when", "where", "which", "who", "does", "this", "that", "with", "from",
    "have", "has", "into", "about", "work", "works", "code", "file", "files", "function", "class",
    "explain", "tell", "show", "give", "should", "would", "could", "first", "read", "main", "part",
    "parts", "together", "fit", "there", "their", "them", "then", "than", "its", "it's", "is", "it",
    "in", "on", "of", "to", "do", "me", "my", "a", "an", "be", "or", "if", "so", "as", "at", "by",
    "please", "simple", "simpler", "terms", "example", "practical", "mean", "means", "repo",
    "repository", "project", "codebase", "used", "using", "get", "gets", "line", "lines",
}


_DEFINITION = re.compile(r"\s*(?:async\s+)?(?:def|class)\s+([a-z_0-9]+)")


def is_text_file(path: Path) -> bool:
    if path.name in _LOCKFILES:
        return False
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES


def list_source_files(repo_path: str | Path) -> list[dict[str, Any]]:
    """Every readable text file in the repo: {path, lines, kind}. Python files first-class."""
    root = Path(repo_path).resolve()
    out: list[dict[str, Any]] = []
    for path in iter_files(root):
        if not is_text_file(path):
            continue
        try:
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                continue
            with path.open("rb") as handle:
                lines = sum(1 for _ in handle)
        except OSError:
            continue
        out.append({
            "path": path.relative_to(root).as_posix(),
            "lines": lines,
            "kind": "python" if path.suffix == ".py" else "other",
        })
        if len(out) >= MAX_LISTED_FILES:
            break
    return out


def _read(root: Path, rel: str) -> str | None:
    target = (root / rel).resolve()
    if root not in target.parents or ".git" in target.parts or not target.is_file():
        return None
    try:
        if target.stat().st_size > MAX_FILE_BYTES:
            return None
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [a.arg for a in node.args.posonlyargs + node.args.args]
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    args += [a.arg for a in node.args.kwonlyargs]
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(args)})"


def _doc(node: ast.AST) -> str:
    doc = ast.get_docstring(node)  # type: ignore[arg-type]
    return doc.strip().splitlines()[0][:140] if doc else ""


def python_outline(source: str, max_items: int = 14) -> list[str]:
    """Top-level classes/functions with their real line numbers and first docstring line."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    items: list[str] = []
    module_doc = _doc(tree)
    if module_doc:
        items.append(f'"""{module_doc}"""')
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            line = f"L{node.lineno}: class {node.name}"
            if methods:
                line += f" (methods: {', '.join(methods[:8])})"
            if _doc(node):
                line += f" - {_doc(node)}"
            items.append(line)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            line = f"L{node.lineno}: {_signature(node)}"
            if _doc(node):
                line += f" - {_doc(node)}"
            items.append(line)
        if len(items) >= max_items:
            items.append("...")
            break
    return items


def rank_by_degree(graph: dict[str, Any] | None) -> list[str]:
    """Module paths, most connected first (the files most worth understanding)."""
    if not graph:
        return []
    degree = {n["id"]: 0 for n in graph.get("nodes", [])}
    for edge in graph.get("edges", []):
        for end in (edge["source"], edge["target"]):
            if end in degree:
                degree[end] += 1
    return sorted(degree, key=lambda p: (-degree[p], len(p.split("/")), p))


def graph_neighbors(graph: dict[str, Any] | None, rel_path: str) -> tuple[list[str], list[str]]:
    """(files this one imports, files that import it) - real intra-repo imports."""
    if not graph:
        return [], []
    imports = sorted({e["target"] for e in graph.get("edges", []) if e["source"] == rel_path})
    imported_by = sorted({e["source"] for e in graph.get("edges", []) if e["target"] == rel_path})
    return imports, imported_by


def repo_digest(repo_path: str | Path, graph: dict[str, Any] | None = None,
                max_tree: int = 120, max_outlined: int = 10, max_chars: int = 7000) -> str:
    """A compact, factual picture of the repo: file tree + outlines of its key modules."""
    root = Path(repo_path).resolve()
    files = list_source_files(root)
    parts = [f"Repository `{root.name}`: {len(files)} text files, {sum(1 for f in files if f['kind'] == 'python')} Python."]

    tree = [f"{f['path']} ({f['lines']} lines)" for f in files[:max_tree]]
    if len(files) > max_tree:
        tree.append(f"... and {len(files) - max_tree} more files")
    parts.append("Files:\n" + "\n".join(tree))

    ranked = rank_by_degree(graph) or [f["path"] for f in files if f["kind"] == "python"]
    outlined = 0
    blocks = []
    for rel in ranked:
        if outlined >= max_outlined:
            break
        if rel.endswith("__init__.py"):
            continue
        source = _read(root, rel)
        if not source:
            continue
        outline = python_outline(source)
        if not outline:
            continue
        imports, imported_by = graph_neighbors(graph, rel)
        header = f"## {rel}"
        if imports:
            header += f"\nimports: {', '.join(imports[:6])}"
        if imported_by:
            header += f"\nimported by: {', '.join(imported_by[:6])}"
        blocks.append(header + "\n" + "\n".join(outline))
        outlined += 1
    if blocks:
        parts.append("Key modules (outline with real line numbers):\n\n" + "\n\n".join(blocks))
    return "\n\n".join(parts)[:max_chars]


def _query_terms(text: str) -> list[str]:
    """Identifiers and meaningful words from a learner's question."""
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
    terms: list[str] = []
    for word in raw:
        pieces = {word.lower()}
        pieces.update(p.lower() for p in re.split(r"_+", word) if len(p) > 2)
        pieces.update(p.lower() for p in re.findall(r"[A-Z]?[a-z]{3,}", word))
        for piece in sorted(pieces):
            if piece not in _STOPWORDS and piece not in terms:
                terms.append(piece)
    return terms[:14]


def find_relevant_files(repo_path: str | Path, question: str, limit: int = 3,
                        exclude: set[str] | None = None) -> list[dict[str, Any]]:
    """Files that most plausibly answer `question`, with the line numbers that matched.

    Scoring is deliberately simple and explainable: a term in the file's path counts most, then
    a term in a `def`/`class` line, then any other occurrence (capped)."""
    terms = _query_terms(question)
    if not terms:
        return []
    root = Path(repo_path).resolve()
    exclude = exclude or set()
    # A path written out in the question ("app/services/store.py") is an explicit request.
    mentioned = {m.lower() for m in re.findall(r"[\w./\\-]+\.\w{1,5}", question)}
    scored: list[tuple[float, str, list[int]]] = []
    for entry in list_source_files(root):
        rel = entry["path"]
        if rel in exclude:
            continue
        source = _read(root, rel)
        if source is None:
            continue
        path_lower = rel.lower()
        score = 0.0
        if any(path_lower.endswith(m.replace("\\", "/")) for m in mentioned):
            score += 40
        stem = Path(rel).stem.lower()
        for term in terms:
            if term == stem:
                score += 12
            elif term in path_lower:
                score += 5
        hits: list[int] = []
        definition_score = 0.0
        body_score = 0.0
        for number, line in enumerate(source.splitlines(), 1):
            lowered = line.lower()
            matched = [t for t in terms if t in lowered]
            if not matched:
                continue
            defined = _DEFINITION.match(lowered)
            if defined:
                # The file that *defines* the thing being asked about beats files that merely
                # mention it: "where is Item defined?" should land on `class Item`.
                name = defined.group(1)
                definition_score += sum(20 if t == name else 6 for t in matched if t in name)
                hits.insert(0, number)
            else:
                body_score += len(matched)
                if len(hits) < 4:
                    hits.append(number)
        score += min(definition_score, 45) + min(body_score, 15)
        hits = sorted(set(hits[:6]))
        if entry["kind"] != "python":
            score *= 0.6
        parts = rel.lower().split("/")
        if parts[-1].startswith("test_") or any(p in ("tests", "test") for p in parts[:-1]):
            score *= 0.5  # tests mention everything; the implementation is the better answer
        if score >= 6:
            scored.append((score, rel, hits))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{"path": rel, "lines": hits, "score": round(score, 1)} for score, rel, hits in scored[:limit]]


def numbered_excerpt(repo_path: str | Path, rel_path: str, focus: list[int] | tuple[int, int] | None = None,
                     max_lines: int = 160, context: int = 12) -> tuple[str, int] | None:
    """Line-numbered source for the model. With `focus` (line numbers, or a (start, end) range)
    only the windows around those lines are included, so a 2,000-line file still fits and the
    part the learner is asking about is never the part that gets cut off.
    Returns (text, total_lines)."""
    root = Path(repo_path).resolve()
    source = _read(root, rel_path.lstrip("/\\"))
    if source is None:
        return None
    lines = source.splitlines()
    total = len(lines)
    if total <= max_lines or not focus:
        shown = lines[:max_lines]
        text = "\n".join(f"{i}: {line}" for i, line in enumerate(shown, 1))
        if total > max_lines:
            text += f"\n... ({total - max_lines} more lines not shown)"
        return text, total

    if isinstance(focus, tuple):
        wanted = set(range(max(1, focus[0] - context), min(total, focus[1] + context) + 1))
    else:
        wanted = set()
        for number in focus:
            wanted.update(range(max(1, number - context), min(total, number + context) + 1))
    # Always keep the top of the file (imports / module docstring) for orientation.
    wanted.update(range(1, min(total, 15) + 1))
    ordered = sorted(wanted)[:max_lines]
    out: list[str] = []
    previous = 0
    for number in ordered:
        if number != previous + 1:
            out.append("...")
        out.append(f"{number}: {lines[number - 1]}")
        previous = number
    if previous < total:
        out.append("...")
    return "\n".join(out), total

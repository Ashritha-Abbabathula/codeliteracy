"""Checks on what the AI tutor says, with no model involved.

The tutor is told to name the files and line numbers it is talking about. A model can invent a file that does not exist or
a line range past the end of a real file. `check_references` reads the repository on disk and counts how many of the
references in a reply are real, so "hallucinated reference rate" is a number, not an impression.

    check_references(repo_path, reply) -> {"cited": 4, "valid": 3, "bad": [{"ref": "app/ghost.py lines 3-9", "why": "no such file"}]}
"""
import re
from pathlib import Path
from typing import Any

_EXT = r"(?:py|md|txt|toml|cfg|ini|json|ya?ml|js|jsx|ts|tsx|html|css)"
_PATH = rf"[\w][\w./\\-]*\.{_EXT}"
# `app/main.py` lines 12-18  |  app/main.py line 12  |  app/main.py:12-18  |  app/main.py (lines 12-18)
_WITH_LINES = re.compile(
    rf"`?(?P<path>{_PATH})`?\s*(?:[:,(]\s*)?(?:(?:lines?|L)\s*)?(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?", re.IGNORECASE)
_LINES_WORD = re.compile(
    rf"`?(?P<path>{_PATH})`?\s*[,(]?\s*(?:lines?|L)\s*(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?", re.IGNORECASE)
_BACKTICKED_FILE = re.compile(rf"`(?P<path>{_PATH})`")


def find_references(reply: str) -> list[dict[str, Any]]:
    """Every file the reply names, with the line range if it gave one. Each reference appears once."""
    found: dict[tuple, dict[str, Any]] = {}
    for rx in (_LINES_WORD, re.compile(rf"(?P<path>{_PATH}):(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?")):
        for m in rx.finditer(reply):
            a = int(m["a"])
            b = int(m["b"]) if m["b"] else a
            found[(m["path"], a, b)] = {"path": m["path"], "start": a, "end": b, "text": m.group(0).strip("` ")}
    with_lines = {path for path, *_ in found}
    for m in _BACKTICKED_FILE.finditer(reply):          # a file named without lines, e.g. `app/main.py`
        if m["path"] not in with_lines:
            found[(m["path"], None, None)] = {"path": m["path"], "start": None, "end": None, "text": m["path"]}
    return list(found.values())


def _resolve(repo_root: Path, rel: str) -> Path | None:
    candidate = (repo_root / rel.replace("\\", "/").lstrip("/")).resolve()
    root = repo_root.resolve()
    if candidate != root and root not in candidate.parents:
        return None  # a reference that points outside the repository is never valid
    return candidate if candidate.is_file() else None


def check_references(repo_path: str | Path, reply: str) -> dict[str, Any]:
    root = Path(repo_path)
    bad: list[dict[str, str]] = []
    refs = find_references(reply)
    for ref in refs:
        target = _resolve(root, ref["path"])
        if target is None:
            bad.append({"ref": ref["text"], "why": "no such file in the repository"})
            continue
        if ref["start"] is None:
            continue
        total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        if ref["start"] < 1 or ref["end"] < ref["start"] or ref["end"] > total:
            bad.append({"ref": ref["text"], "why": f"lines outside the file (it has {total})"})
    return {"cited": len(refs), "valid": len(refs) - len(bad), "bad": bad}


def hallucinated_reference_rate(results: list[dict[str, Any]]) -> float | None:
    """Across many tutor replies: the share of references that were not real."""
    cited = sum(r["cited"] for r in results)
    return round(sum(len(r["bad"]) for r in results) / cited, 3) if cited else None

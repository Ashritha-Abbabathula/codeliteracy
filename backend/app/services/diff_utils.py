"""Line-level diffs (with context) for showing exactly what an AI change touched."""

import difflib
from typing import Any

CONTEXT = 3
MAX_LINES_PER_FILE = 500


def build_file_diff(path: str, before: str | None, after: str) -> dict[str, Any]:
    """`before` is None for a newly created file. Returns the FileDiff shape: add/del lines
    with real old/new line numbers, `ctx` lines around each change, `gap` rows between
    distant hunks."""
    old = (before or "").splitlines()
    new = after.splitlines()
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)

    lines: list[dict[str, Any]] = []
    added = removed = 0
    for group in matcher.get_grouped_opcodes(CONTEXT):
        if lines:
            lines.append({"kind": "gap", "old_no": None, "new_no": None, "text": ""})
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for k in range(i2 - i1):
                    lines.append({"kind": "ctx", "old_no": i1 + k + 1, "new_no": j1 + k + 1, "text": old[i1 + k]})
                continue
            for k in range(i1, i2):
                removed += 1
                lines.append({"kind": "del", "old_no": k + 1, "new_no": None, "text": old[k]})
            for k in range(j1, j2):
                added += 1
                lines.append({"kind": "add", "old_no": None, "new_no": k + 1, "text": new[k]})

    if len(lines) > MAX_LINES_PER_FILE:
        lines = lines[:MAX_LINES_PER_FILE]
        lines.append({"kind": "gap", "old_no": None, "new_no": None, "text": "… diff truncated …"})

    return {
        "path": path,
        "is_new_file": before is None,
        "added": added,
        "removed": removed,
        "lines": lines,
    }


def diff_excerpt(diffs: list[dict[str, Any]], limit: int = 6000) -> str:
    """Compact unified-style text of a set of diffs, for giving the quiz generator the real
    code that changed."""
    out: list[str] = []
    for d in diffs:
        out.append(f"--- {d['path']}{' (new file)' if d['is_new_file'] else ''}")
        for line in d["lines"]:
            if line["kind"] == "add":
                out.append(f"+ {line['text']}")
            elif line["kind"] == "del":
                out.append(f"- {line['text']}")
            elif line["kind"] == "gap":
                out.append("...")
    return "\n".join(out)[:limit]

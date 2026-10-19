"""Line-by-line file breakdown + comprehension quiz for the Code Inspector.

The AI produces an overview, line-range sections and 3-4 questions in one call. Every
line range is validated against the real file before it's shown. If the AI is unavailable
the result is flagged `degraded` and falls back to what can be *known* without it - the
file's real structure from the AST (functions/classes and their true line ranges, plus
docstrings) - never to invented explanations or canned quiz questions."""

import ast
import hashlib
from pathlib import Path
from typing import Any

from app.services.llm_client import LLMCallError, LLMNotConfiguredError, json_object
from app.services.quiz_service import QuizError, clean_quiz, generate_quizzes_for_file

MAX_ANALYZED_LINES = 600  # lines sent to the model for the section-by-section walkthrough
MAX_RETURNED_LINES = 2500  # lines returned to the viewer
MAX_FILE_BYTES = 400_000
MAX_EXPLAIN_RANGE = 80  # lines a learner can ask to have explained at once

_FILE_EXPLAINER_PROMPT = """\
You are CodeLiteracy's Code Explainer and Tutor. A developer who is new to this codebase \
(and may be new to some of the ideas in it) wants to understand this one source file. Walk \
them through it section by section, then test their comprehension.

Output strict JSON only, matching this schema:
{
  "overview": "2-3 sentences: this file's job, and how it fits with the files it imports / is imported by.",
  "key_concepts": [{"term": "a concept or term a newcomer may not know", "meaning": "one plain sentence, as it applies in this file"}],
  "line_sections": [
    {"start_line": 1, "end_line": 15, "title": "short title",
     "explanation": "what these lines do, WHY they are written this way, and anything easy to misread",
     "importance": "setup"}
  ],
  "quizzes": [
    {"concept": "short concept name (2-5 words)", "question": "...",
     "options": ["A", "B", "C", "D"], "correct_index": 0,
     "option_explanations": ["why option 0 is right or wrong", "... 1", "... 2", "... 3"],
     "hint": "a nudge toward where to look or what to think about, without giving the answer away",
     "explanation": "2-3 sentences teaching why the correct option is right, in terms of this code",
     "search_query": "a web search a beginner could use to learn this concept"}
  ]
}

Rules for line_sections:
- Cover the analyzed lines in order with no large gaps: one section per logical unit (the \
imports, each function or class, each distinct block). Typically 4-12 sections; never lump \
several functions into one section. start_line/end_line are 1-indexed and must match the line \
numbers shown. importance is one of: setup, core, handler, utility.
- Each explanation: 2-4 sentences in plain words. Say what the code does, then why (the \
problem it solves, or what would go wrong without it). Use the real names from the code in \
backticks. Define jargon the first time you use it. No filler like "this section contains code".
- Only state what the code shows. If something depends on another file you can't see, say so.

Rules for key_concepts: 2-5 entries, only ideas actually used in this file.

Rules for quizzes: exactly 4 questions with 4 options each, answerable from THIS file. Test \
behaviour and reasoning (what happens for a given input, why a check exists, what breaks if a \
line is removed), not syntax trivia or names. Each wrong option is a mistake a real learner \
would make. option_explanations has 4 entries in the same order as options. correct_index is 0-based.

Do not wrap the JSON in markdown fences."""

_EXPLAIN_LINES_PROMPT = """\
You are CodeLiteracy's Code Tutor. A learner has selected some lines of a source file and \
asked "explain exactly these lines". Explain them the way a patient senior developer would at \
someone's desk: concretely, in plain words, in order.

Output strict JSON only:
{
  "summary": "1-2 sentences: what the selected lines accomplish as a whole and why they exist",
  "notes": [{"start_line": 12, "end_line": 12, "explanation": "what this line (or small group of lines) does and why"}],
  "concepts": [{"term": "a term or language feature used here that a newcomer may not know", "meaning": "one plain sentence"}]
}

Rules:
- notes go through the SELECTED lines in order, one note per line or per small group of \
closely related lines (blank lines and lone brackets need no note). Line numbers must be \
inside the selected range.
- For each note: say what happens when this code runs, name the real values/variables \
involved in backticks, and add the "why" where it isn't obvious. If a line calls something \
defined elsewhere, say what that call is for (and that its body isn't shown, if it isn't).
- The surrounding lines are given only as context; do not explain them.
- concepts: 0-4 entries. Do not wrap the JSON in markdown fences."""


def read_source(repo_path_str: str, rel_path: str) -> tuple[Path, str]:
    """Read a file inside the repo, refusing anything that escapes it."""
    repo_root = Path(repo_path_str).resolve()
    target = (repo_root / rel_path.lstrip("/\\")).resolve()
    if repo_root not in target.parents:
        raise ValueError(f"Path outside repository: {rel_path}")
    if ".git" in target.parts:
        raise ValueError("Refusing to read inside the .git directory.")
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {rel_path}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{rel_path} is too large to walk through ({target.stat().st_size // 1024} KB).")
    return target, target.read_text(encoding="utf-8", errors="replace")


def content_hash(content: str) -> str:
    return hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()


def _clean_sections(raw: Any, analyzed_lines: int) -> list[dict[str, Any]]:
    """Keep only sections whose line ranges are real, clamped to the file, in order."""
    sections: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return sections
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = int(item["start_line"])
            end = int(item["end_line"])
        except (KeyError, TypeError, ValueError):
            continue
        start = max(1, start)
        end = min(analyzed_lines, end)
        if start > end:
            continue
        title = str(item.get("title") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        if not title or not explanation:
            continue
        importance = item.get("importance")
        sections.append({
            "start_line": start,
            "end_line": end,
            "title": title[:120],
            "explanation": explanation,
            "importance": importance if importance in ("setup", "core", "handler", "utility") else "core",
        })
    sections.sort(key=lambda s: s["start_line"])
    return sections


def _docstring_first_line(node: ast.AST) -> str | None:
    doc = ast.get_docstring(node)  # type: ignore[arg-type]
    return doc.strip().splitlines()[0] if doc else None


def structural_sections(content: str, rel_path: str) -> list[dict[str, Any]]:
    """Honest, AI-free breakdown: real top-level structure with true line ranges."""
    lines = content.splitlines()
    total = len(lines)
    if total == 0:
        return []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        tree = None

    sections: list[dict[str, Any]] = []
    if tree is not None:
        import_block_end = 0
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_block_end = node.end_lineno or node.lineno
            elif not (isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant)):
                break
        if import_block_end:
            sections.append({
                "start_line": 1, "end_line": import_block_end,
                "title": "Module docstring and imports" if _docstring_first_line(tree) else "Imports",
                "explanation": _docstring_first_line(tree) or "Modules and names this file depends on.",
                "importance": "setup",
            })
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            end = node.end_lineno or node.lineno
            if isinstance(node, ast.ClassDef):
                title = f"class {node.name}"
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                detail = f"Defines {len(methods)} method(s): {', '.join(methods[:6])}." if methods else "Class definition."
            else:
                args = ", ".join(a.arg for a in node.args.args)
                title = f"def {node.name}({args})"
                detail = "Function definition."
            sections.append({
                "start_line": start, "end_line": end,
                "title": title[:120],
                "explanation": _docstring_first_line(node) or f"{detail} (No docstring in the source.)",
                "importance": "core",
            })
    if not sections:
        chunk = max(20, -(-total // 6))
        for start in range(1, total + 1, chunk):
            sections.append({
                "start_line": start, "end_line": min(total, start + chunk - 1),
                "title": f"Lines {start}-{min(total, start + chunk - 1)}",
                "explanation": "AI explanation unavailable for this section.",
                "importance": "core",
            })
    return sections


def _module_overview(content: str, rel_path: str, total: int) -> str:
    try:
        doc = _docstring_first_line(ast.parse(content))
    except SyntaxError:
        doc = None
    return doc or f"{rel_path} ({total} lines)."


def _clean_concepts(raw: Any, limit: int = 6) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                term = str(item.get("term") or "").strip()
                meaning = str(item.get("meaning") or "").strip()
                if term and meaning:
                    out.append({"term": term[:80], "meaning": meaning[:400]})
    return out[:limit]


def _fill_uncovered(sections: list[dict[str, Any]], content: str, rel_path: str, analyzed: int) -> list[dict[str, Any]]:
    """Add the file's real structure for the part the AI didn't walk through (beyond the
    analyzed lines), flagged `needs_explanation` so the viewer can offer to explain it on
    request instead of leaving the bottom of a long file blank."""
    extra = [
        {**s, "needs_explanation": True}
        for s in structural_sections(content, rel_path)
        if s["start_line"] > analyzed
    ]
    return sections + extra


def analyze_file(repo_path_str: str, rel_path: str, imports: list[str] | None = None,
                 imported_by: list[str] | None = None) -> dict[str, Any]:
    """Returns file_path, total_lines, content, sha, overview, key_concepts, line_sections,
    quizzes (each with correct_index/explanation, for the caller to persist - never sent to the
    client as is), degraded (bool), notice (str|None), truncated (bool).

    `imports` / `imported_by` are this file's real neighbours in the dependency graph, so the
    overview can say how it fits in rather than guess."""
    _, raw = read_source(repo_path_str, rel_path)
    lines = raw.splitlines()
    total = len(lines)
    analyzed = min(total, MAX_ANALYZED_LINES)
    returned = raw if total <= MAX_RETURNED_LINES else "\n".join(lines[:MAX_RETURNED_LINES])
    viewer_content = "\n".join(lines[:MAX_RETURNED_LINES])

    base: dict[str, Any] = {
        "file_path": rel_path,
        "total_lines": min(total, MAX_RETURNED_LINES),
        "content": returned,
        "sha": content_hash(raw),
        "truncated": total > MAX_RETURNED_LINES,
        "analyzed_lines": analyzed,
        "key_concepts": [],
    }

    numbered = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines[:analyzed]))
    note = f"\n(Only the first {analyzed} of {total} lines are shown; cover only those.)" if total > analyzed else ""
    neighbours = ""
    if imports:
        neighbours += f"\nThis file imports from these files in the repo: {', '.join(imports[:10])}"
    if imported_by:
        neighbours += f"\nIt is imported by: {', '.join(imported_by[:10])}"
    prompt = f"File: {rel_path} ({total} lines total){note}{neighbours}\n\nSource (with line numbers):\n{numbered}"

    try:
        parsed = json_object(_FILE_EXPLAINER_PROMPT, prompt, max_tokens=8000)
    except (LLMNotConfiguredError, LLMCallError) as exc:
        return {
            **base,
            "overview": _module_overview(raw, rel_path, total),
            "line_sections": structural_sections(viewer_content, rel_path),
            "quizzes": [],
            "degraded": True,
            "notice": f"AI walkthrough unavailable: {exc} Showing the file's structure instead.",
        }

    sections = _clean_sections(parsed.get("line_sections"), analyzed)
    overview = str(parsed.get("overview") or "").strip()
    quizzes = [q for q in (clean_quiz(item) for item in (parsed.get("quizzes") or [])) if q][:4]

    notice = None
    if len(quizzes) < 3:
        try:
            quizzes = generate_quizzes_for_file(rel_path, overview, numbered)
        except QuizError as exc:
            quizzes = []
            notice = f"Quiz unavailable: {exc}"

    degraded = not sections or not overview
    if sections and total > analyzed:
        sections = _fill_uncovered(sections, viewer_content, rel_path, analyzed)
        notice = notice or (
            f"This is a long file: the AI walked through the first {analyzed} lines. "
            "For anything below that, select the lines and choose “Explain selected lines”."
        )
    return {
        **base,
        "overview": overview or _module_overview(raw, rel_path, total),
        "key_concepts": _clean_concepts(parsed.get("key_concepts")),
        "line_sections": sections or structural_sections(viewer_content, rel_path),
        "quizzes": quizzes,
        "degraded": degraded,
        "notice": notice or ("AI explanations were incomplete; showing the file's structure." if degraded else None),
    }


class ExplainError(Exception):
    pass


def explain_lines(repo_path_str: str, rel_path: str, start_line: int, end_line: int) -> dict[str, Any]:
    """A focused, line-by-line explanation of an arbitrary range the learner selected.
    Raises ValueError for a bad range and ExplainError if the AI can't answer (no canned
    substitute: an invented explanation of someone's code is worse than an honest error)."""
    _, raw = read_source(repo_path_str, rel_path)
    lines = raw.splitlines()
    total = len(lines)
    if start_line > end_line:
        start_line, end_line = end_line, start_line
    if total == 0 or start_line < 1 or start_line > total:
        raise ValueError("Those lines aren't in this file.")
    end_line = min(end_line, total)
    if end_line - start_line + 1 > MAX_EXPLAIN_RANGE:
        raise ValueError(f"Select at most {MAX_EXPLAIN_RANGE} lines at a time.")

    before = max(1, start_line - 25)
    after = min(total, end_line + 15)
    numbered = "\n".join(
        f"{'>>' if start_line <= n <= end_line else '  '} {n}: {lines[n - 1]}" for n in range(before, after + 1)
    )
    head = ""
    if before > 1:  # keep the imports in view: they explain half the names used below
        head = "Top of the file:\n" + "\n".join(f"   {n}: {lines[n - 1]}" for n in range(1, min(before, 21))) + "\n...\n\n"
    prompt = (
        f"File: {rel_path} ({total} lines). The learner selected lines {start_line}-{end_line} "
        f"(marked with >>).\n\n{head}Code:\n{numbered}"
    )

    try:
        parsed = json_object(_EXPLAIN_LINES_PROMPT, prompt, max_tokens=3000)
    except (LLMNotConfiguredError, LLMCallError) as exc:
        raise ExplainError(str(exc)) from exc

    summary = str(parsed.get("summary") or "").strip()
    notes: list[dict[str, Any]] = []
    for item in parsed.get("notes") or []:
        if not isinstance(item, dict):
            continue
        try:
            a = int(item["start_line"])
            b = int(item.get("end_line", a))
        except (KeyError, TypeError, ValueError):
            continue
        a, b = max(start_line, min(a, b)), min(end_line, max(a, b))
        text = str(item.get("explanation") or "").strip()
        if a <= b and text:
            notes.append({"start_line": a, "end_line": b, "explanation": text})
    notes.sort(key=lambda n: n["start_line"])
    if not summary and not notes:
        raise ExplainError("The AI's explanation came back empty. Please try again.")
    return {
        "file_path": rel_path, "start_line": start_line, "end_line": end_line,
        "summary": summary or "Here is what each of these lines does.",
        "notes": notes, "concepts": _clean_concepts(parsed.get("concepts"), limit=4),
        "sha": content_hash(raw),
    }

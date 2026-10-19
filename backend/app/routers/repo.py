import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_optional, get_owned_repo, owned_by, owner_id
from app.models import Quiz, Repository, User
from app.models import AssistantChange
from app.schemas import (
    DependencyGraph,
    ExplainFileRequest,
    ExplainLinesRequest,
    ExplainLinesResponse,
    FileExplanation,
    RepoConnectRequest,
    RepoConnectResponse,
    RepoExplanation,
    RepoFile,
    RepoInfo,
    RepoProgress,
)
from app.services.code_explainer_service import (
    MAX_RETURNED_LINES,
    ExplainError,
    analyze_file,
    content_hash,
    explain_lines,
    read_source,
)
from app.services.dependency_graph import Graph, build_dependency_graph
from app.services.explainer import ExplanationError, generate_explanations, generate_file_explanation
from app.services.flowchart_service import generate_architecture_flowchart
from app.services.github_service import SELF_SAMPLE_SOURCE, RepoConnectionError, connect_repository
from app.services.onboarding_service import generate_repo_onboarding, learning_path_for
from app.services.quiz_store import new_quiz_row, to_items
from app.services.repo_context import graph_neighbors, list_source_files

router = APIRouter(prefix="/api/repo", tags=["repo"])


class FileDetailRequest(BaseModel):
    path: str


@router.get("/samples")
def get_sample_repositories() -> list[dict[str, str]]:
    """One-click sample repositories."""
    samples = [
        {
            "id": "sample-requests",
            "name": "Requests (HTTP library)",
            "source": "https://github.com/psf/requests",
            "description": "Python's most-used HTTP library: a clear, well-layered codebase with real dependency structure.",
            "tech": "Python, HTTP, urllib3",
        },
        {
            "id": "sample-nanogpt",
            "name": "nanoGPT",
            "source": "https://github.com/karpathy/nanoGPT",
            "description": "A minimal GPT implementation and training loop in a handful of readable files.",
            "tech": "Python, PyTorch, Transformers",
        },
    ]
    if (Path(__file__).resolve().parents[3] / "backend" / "app").is_dir():
        samples.insert(0, {
            "id": "sample-codeliteracy",
            "name": "CodeLiteracy (this project)",
            "source": SELF_SAMPLE_SOURCE,
            "description": "Explore CodeLiteracy itself: how the FastAPI backend, Gemini client and quiz engine fit together. (A safe copy, so the AI assistant can experiment freely.)",
            "tech": "FastAPI, SQLAlchemy, Gemini AI",
        })
    return samples


@router.get("/user/list", response_model=list[RepoInfo])
def list_user_repositories(
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[RepoInfo]:
    stmt = select(Repository).where(owned_by(Repository.user_id, user)).order_by(Repository.connected_at.desc()).limit(10)
    return [
        RepoInfo(repo_id=r.id, name=r.name, source=r.source, connected_at=r.connected_at)
        for r in db.scalars(stmt)
    ]


@router.post("/connect", response_model=RepoConnectResponse)
def connect(
    payload: RepoConnectRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> RepoConnectResponse:
    """Clone/link the repo, then parse it into a dependency graph."""
    if not payload.source.strip():
        raise HTTPException(status_code=400, detail="Enter a GitHub URL or a local folder path.")
    try:
        name, local_path = connect_repository(payload.source)
    except RepoConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    graph = build_dependency_graph(local_path)
    if not graph.nodes:
        raise HTTPException(
            status_code=422,
            detail="No Python files found in this repository. CodeLiteracy currently analyzes Python projects.",
        )

    repository = Repository(
        user_id=owner_id(user),
        source="CodeLiteracy (safe copy)" if payload.source.strip() == SELF_SAMPLE_SOURCE else payload.source.strip(),
        name=name,
        local_path=local_path,
        graph_json=json.dumps({"nodes": graph.nodes, "edges": graph.edges}),
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

    return RepoConnectResponse(
        repo_id=repository.id,
        name=repository.name,
        source=repository.source,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        graph=DependencyGraph(nodes=graph.nodes, edges=graph.edges),
    )


@router.get("/{repo_id}/info", response_model=RepoInfo)
def get_info(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> RepoInfo:
    repo = get_owned_repo(db, repo_id, user)
    return RepoInfo(repo_id=repo.id, name=repo.name, source=repo.source, connected_at=repo.connected_at)


@router.get("/{repo_id}/onboarding")
def get_onboarding(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Conversational onboarding: main idea, tech stack, easy vs. hard, folder guide."""
    repository = get_owned_repo(db, repo_id, user)
    graph = json.loads(repository.graph_json) if repository.graph_json else None
    if repository.onboarding_json:
        cached = json.loads(repository.onboarding_json)
        if "learning_path" not in cached:  # analysed by an older version: add the reading order
            cached["learning_path"] = learning_path_for(repository.local_path, graph)
            repository.onboarding_json = json.dumps(cached)
            db.commit()
        return cached

    onboarding = generate_repo_onboarding(repository.local_path, graph)
    if not onboarding.get("degraded"):  # never cache a fallback: retry should reach the AI
        repository.onboarding_json = json.dumps(onboarding)
        db.commit()
    return onboarding


@router.get("/{repo_id}/flowchart")
def get_flowchart(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The clean, layered architecture flowchart."""
    repository = get_owned_repo(db, repo_id, user)
    if repository.flowchart_json:
        return json.loads(repository.flowchart_json)

    flowchart = generate_architecture_flowchart(repository.local_path)
    if not flowchart.get("degraded"):
        repository.flowchart_json = json.dumps(flowchart)
        db.commit()
    return flowchart


RANGE_CACHE_KEY = "__ranges__"  # lives beside the per-file entries in file_details_json
MAX_CACHED_RANGES = 150


def _file_cache(repository: Repository) -> dict[str, Any]:
    return json.loads(repository.file_details_json or "{}")


@router.get("/{repo_id}/files", response_model=list[RepoFile])
def list_files(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[RepoFile]:
    """Every readable file in the repo (so any of them can be opened, not only the modules
    that made it onto the flowchart), with the learner's progress on each."""
    repository = get_owned_repo(db, repo_id, user)
    explored = {path for path in _file_cache(repository) if path != RANGE_CACHE_KEY}
    totals: dict[str, list[int]] = {}
    rows = db.execute(
        select(Quiz.file_path, Quiz.solved).where(
            Quiz.repo_id == repo_id, Quiz.change_id.is_(None), Quiz.replaced_by.is_(None)
        )
    )
    for file_path, solved in rows:
        if file_path:
            counts = totals.setdefault(file_path, [0, 0])
            counts[0] += 1
            counts[1] += 1 if solved else 0
    return [
        RepoFile(
            path=f["path"], lines=f["lines"], kind=f["kind"], explored=f["path"] in explored,
            questions=totals.get(f["path"], [0, 0])[0], solved=totals.get(f["path"], [0, 0])[1],
        )
        for f in list_source_files(repository.local_path)
    ]


@router.get("/{repo_id}/progress", response_model=RepoProgress)
def get_progress(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> RepoProgress:
    """How far the learner has got with this repository."""
    repository = get_owned_repo(db, repo_id, user)
    graph = json.loads(repository.graph_json or '{"nodes": []}')
    explored = [path for path in _file_cache(repository) if path != RANGE_CACHE_KEY]
    quizzes = list(db.scalars(select(Quiz).where(Quiz.repo_id == repo_id, Quiz.replaced_by.is_(None))))
    changes = list(db.scalars(
        select(AssistantChange.id).where(AssistantChange.repo_id == repo_id, AssistantChange.reverted.is_(False))
    ))
    return RepoProgress(
        files_total=len([n for n in graph["nodes"] if not n["id"].endswith("__init__.py")]) or len(graph["nodes"]),
        files_explored=len(explored),
        questions_total=len(quizzes),
        questions_answered=sum(1 for q in quizzes if (q.attempts or 0) > 0),
        questions_solved=sum(1 for q in quizzes if q.solved),
        changes_made=len(changes),
    )


@router.post("/{repo_id}/file-details")
def get_file_details(
    repo_id: str,
    payload: FileDetailRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """File content + section-by-section breakdown + 3-4 MCQs. The analysis is cached against a
    hash of the file's content (so it's instant on re-open and refreshes if the file changes),
    and the quizzes are stored server-side so answers are verified there."""
    repository = get_owned_repo(db, repo_id, user)
    try:
        _, content = read_source(repository.local_path, payload.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cache = _file_cache(repository)
    entry = cache.get(payload.path)
    sha = content_hash(content)
    graph = json.loads(repository.graph_json) if repository.graph_json else None
    imports, imported_by = graph_neighbors(graph, payload.path)

    if isinstance(entry, dict) and entry.get("sha") == sha:
        quizzes = [q for q in (db.get(Quiz, qid) for qid in entry.get("quiz_ids", [])) if q]
        if quizzes:
            lines = content.splitlines()
            return {
                "file_path": payload.path,
                "total_lines": min(len(lines), MAX_RETURNED_LINES),
                "content": "\n".join(lines[:MAX_RETURNED_LINES]) if len(lines) > MAX_RETURNED_LINES else content,
                "overview": entry["overview"],
                "key_concepts": entry.get("key_concepts", []),
                "line_sections": entry["line_sections"],
                "quizzes": [q.model_dump() for q in to_items(quizzes)],
                "degraded": False,
                "notice": entry.get("notice"),
                "truncated": len(lines) > MAX_RETURNED_LINES,
                "imports": imports,
                "imported_by": imported_by,
            }

    result = analyze_file(repository.local_path, payload.path, imports, imported_by)

    quizzes = [
        new_quiz_row(q, user_id=repository.user_id, repo_id=repo_id, file_path=payload.path)
        for q in result["quizzes"]
    ]
    db.add_all(quizzes)
    db.flush()

    if not result["degraded"] and quizzes:
        cache[payload.path] = {
            "sha": result["sha"], "overview": result["overview"],
            "key_concepts": result["key_concepts"],
            "line_sections": result["line_sections"], "quiz_ids": [q.id for q in quizzes],
            "notice": result["notice"],
        }
        repository.file_details_json = json.dumps(cache)
    db.commit()

    return {
        "file_path": result["file_path"],
        "total_lines": result["total_lines"],
        "content": result["content"],
        "overview": result["overview"],
        "key_concepts": result["key_concepts"],
        "line_sections": result["line_sections"],
        "quizzes": [q.model_dump() for q in to_items(quizzes)],
        "degraded": result["degraded"],
        "notice": result["notice"],
        "truncated": result["truncated"],
        "imports": imports,
        "imported_by": imported_by,
    }


@router.post("/{repo_id}/explain-lines", response_model=ExplainLinesResponse)
def explain_selected_lines(
    repo_id: str,
    payload: ExplainLinesRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> ExplainLinesResponse:
    """Line-by-line explanation of exactly the lines the learner selected - including parts of
    a long file the section walkthrough didn't reach. Cached per (file content, range)."""
    repository = get_owned_repo(db, repo_id, user)
    try:
        _, content = read_source(repository.local_path, payload.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    start, end = sorted((payload.start_line, payload.end_line))
    cache = _file_cache(repository)
    ranges: dict[str, Any] = cache.get(RANGE_CACHE_KEY) or {}
    key = f"{payload.path}|{content_hash(content)}|{start}-{end}"
    if key in ranges:
        return ExplainLinesResponse(**ranges[key], cached=True)

    try:
        result = explain_lines(repository.local_path, payload.path, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExplainError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result.pop("sha", None)

    ranges[key] = result
    while len(ranges) > MAX_CACHED_RANGES:  # oldest first (dicts keep insertion order)
        ranges.pop(next(iter(ranges)))
    cache[RANGE_CACHE_KEY] = ranges
    repository.file_details_json = json.dumps(cache)
    db.commit()
    return ExplainLinesResponse(**result)


@router.get("/{repo_id}/graph", response_model=DependencyGraph)
def get_graph(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> DependencyGraph:
    """The raw file-level dependency graph."""
    repository = get_owned_repo(db, repo_id, user)
    data = json.loads(repository.graph_json or '{"nodes": [], "edges": []}')
    return DependencyGraph(nodes=data["nodes"], edges=data["edges"])


@router.post("/{repo_id}/explain", response_model=RepoExplanation)
def explain(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> RepoExplanation:
    """A plain-language walkthrough of the repo and each file's purpose."""
    repository = get_owned_repo(db, repo_id, user)
    if repository.explanations_json is not None:
        return RepoExplanation(**json.loads(repository.explanations_json))

    graph_data = json.loads(repository.graph_json or '{"nodes": [], "edges": []}')
    graph = Graph(nodes=graph_data["nodes"], edges=graph_data["edges"])
    try:
        explanation = generate_explanations(repository.local_path, graph)
    except ExplanationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    repository.explanations_json = json.dumps(explanation)
    db.commit()
    return RepoExplanation(**explanation)


@router.post("/{repo_id}/explain/file", response_model=FileExplanation)
def explain_file(
    repo_id: str,
    payload: ExplainFileRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> FileExplanation:
    repository = get_owned_repo(db, repo_id, user)
    explanation = json.loads(repository.explanations_json) if repository.explanations_json else {
        "overview": "",
        "files": [],
    }
    for entry in explanation["files"]:
        if entry["path"] == payload.path:
            return FileExplanation(**entry)

    try:
        text = generate_file_explanation(repository.local_path, payload.path)
    except ExplanationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    explanation["files"].append({"path": payload.path, "explanation": text})
    repository.explanations_json = json.dumps(explanation)
    db.commit()
    return FileExplanation(path=payload.path, explanation=text)

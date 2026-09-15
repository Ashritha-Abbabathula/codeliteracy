import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Repository
from app.schemas import DependencyGraph, RepoConnectRequest, RepoConnectResponse, RepoExplanation
from app.services.dependency_graph import Graph, build_dependency_graph
from app.services.explainer import ExplanationError, generate_explanations
from app.services.github_service import RepoConnectionError, connect_repository

router = APIRouter(prefix="/api/repo", tags=["repo"])


@router.post("/connect", response_model=RepoConnectResponse)
def connect(payload: RepoConnectRequest, db: Session = Depends(get_db)) -> RepoConnectResponse:
    """FR1 + FR2: clone/link the repo, then parse it into a dependency graph."""
    try:
        name, local_path = connect_repository(payload.source)
    except RepoConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    graph = build_dependency_graph(local_path)
    if not graph.nodes:
        raise HTTPException(
            status_code=422,
            detail="No Python files found. CodeLiteracy's initial version only analyzes Python repositories.",
        )

    repository = Repository(
        source=payload.source,
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


@router.get("/{repo_id}/graph", response_model=DependencyGraph)
def get_graph(repo_id: str, db: Session = Depends(get_db)) -> DependencyGraph:
    """FR3: the flowchart viewer fetches the stored graph by repo id."""
    repository = db.get(Repository, repo_id)
    if repository is None or repository.graph_json is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    data = json.loads(repository.graph_json)
    return DependencyGraph(nodes=data["nodes"], edges=data["edges"])


@router.post("/{repo_id}/explain", response_model=RepoExplanation)
def explain(repo_id: str, db: Session = Depends(get_db)) -> RepoExplanation:
    """FR4: a plain-language walkthrough of the repo and each file's purpose.
    Cached after the first call so repeat visits don't re-spend LLM budget."""
    repository = db.get(Repository, repo_id)
    if repository is None or repository.graph_json is None:
        raise HTTPException(status_code=404, detail="Repository not found.")

    if repository.explanations_json is not None:
        return RepoExplanation(**json.loads(repository.explanations_json))

    graph_data = json.loads(repository.graph_json)
    graph = Graph(nodes=graph_data["nodes"], edges=graph_data["edges"])

    try:
        explanation = generate_explanations(repository.local_path, graph)
    except ExplanationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    repository.explanations_json = json.dumps(explanation)
    db.commit()
    return RepoExplanation(**explanation)

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_optional, get_owned_repo, owner_id
from app.models import AssistantChange, Quiz, Repository, User
from app.schemas import (
    ActivityItem,
    AssistantRequest,
    AssistantResponse,
    FileDiff,
    QuizItem,
    UndoResponse,
)
from app.services.assistant_service import AssistantError, run_assistant
from app.services.dependency_graph import build_dependency_graph
from app.services.diff_utils import diff_excerpt
from app.services.github_service import commit_changes
from app.services.quiz_service import QuizError, generate_quizzes_for_change
from app.services.quiz_store import new_quiz_row, to_items

router = APIRouter(prefix="/api", tags=["assistant"])


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def _on_disk(repo_path: str, rel: str) -> str | None:
    target = Path(repo_path) / rel
    if not target.is_file():
        return None
    return target.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")


def _refresh_repo_caches(repository: Repository) -> None:
    """The code just changed, so anything derived from it must not keep describing the old
    code: rebuild the dependency graph now, and drop the cached flowchart/explanations so they
    are regenerated the next time they're opened. (Per-file walkthroughs are keyed by a hash of
    the file's content, so they refresh themselves.)"""
    graph = build_dependency_graph(repository.local_path)
    repository.graph_json = json.dumps({"nodes": graph.nodes, "edges": graph.edges})
    repository.flowchart_json = None
    repository.explanations_json = None


def _generate_change_quizzes(db: Session, change: AssistantChange, repository_user_id: str | None) -> list[Quiz]:
    """3-4 comprehension MCQs on a change, stored server-side (so answers are verified there)."""
    diffs = json.loads(change.diff_json or "[]")
    generated = generate_quizzes_for_change(
        change.concept, change.summary, json.loads(change.steps_json), diff_excerpt(diffs)
    )
    first_file = (json.loads(change.files_changed_json or "[]") or [None])[0]
    rows = [
        new_quiz_row(q, user_id=repository_user_id, repo_id=change.repo_id, file_path=first_file, change_id=change.id)
        for q in generated
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _current_quizzes(db: Session, change_id: str) -> list[Quiz]:
    return list(db.scalars(
        select(Quiz).where(Quiz.change_id == change_id, Quiz.replaced_by.is_(None)).order_by(Quiz.created_at)
    ))


def _can_undo(change: AssistantChange, repo_path: str) -> bool:
    if change.reverted or not change.snapshot_json:
        return False
    snapshot = json.loads(change.snapshot_json)
    for rel, snap in snapshot.items():
        current = _on_disk(repo_path, rel)
        if current is None or _sha(current) != snap["after_sha"]:
            return False
    return bool(snapshot)


def _to_response(change: AssistantChange, quizzes: list[Quiz], repo_path: str, quiz_error: str | None = None) -> AssistantResponse:
    return AssistantResponse(
        change_id=change.id,
        request=change.request,
        summary=change.summary,
        concept=change.concept,
        concept_explanation=change.concept_explanation,
        verify=change.verify,
        steps=json.loads(change.steps_json or "[]"),
        activity=[ActivityItem(**a) for a in json.loads(change.activity_json or "[]")],
        files_changed=json.loads(change.files_changed_json or "[]"),
        diffs=[FileDiff(**d) for d in json.loads(change.diff_json or "[]")],
        quizzes=to_items(quizzes),
        quiz_error=quiz_error,
        commit_sha=change.commit_sha,
        reverted=bool(change.reverted),
        can_undo=_can_undo(change, repo_path),
        created_at=change.created_at,
    )


@router.post("/repo/{repo_id}/assistant", response_model=AssistantResponse)
def ask_assistant(
    repo_id: str,
    payload: AssistantRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> AssistantResponse:
    """Carry out a requested fix/feature, capture real before/after diffs, explain what and
    why, commit exactly the changed files, then generate comprehension questions."""
    repository = get_owned_repo(db, repo_id, user)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty.")
    if len(message) > 2000:
        raise HTTPException(status_code=400, detail="That request is too long (2000 characters max).")

    try:
        result = run_assistant(repository.local_path, message)
    except AssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    commit_sha = commit_changes(
        repository.local_path, f"CodeLiteracy: {result['summary']}", result["files_changed"]
    )

    change = AssistantChange(
        user_id=owner_id(user), repo_id=repo_id, request=message,
        summary=result["summary"], concept=result["concept"],
        concept_explanation=result.get("concept_explanation"), verify=result.get("verify"),
        steps_json=json.dumps(result["steps"]),
        activity_json=json.dumps(result.get("activity", [])),
        files_changed_json=json.dumps(result["files_changed"]),
        diff_json=json.dumps(result["diffs"]),
        snapshot_json=json.dumps({
            path: {"before": result["originals"].get(path), "after_sha": _sha(result["finals"][path])}
            for path in result["files_changed"]
        }),
        commit_sha=commit_sha,
    )
    db.add(change)
    _refresh_repo_caches(repository)
    db.commit()
    db.refresh(change)

    # The change is already applied and committed; a quiz failure must not turn that into an
    # error. Report it so the UI can offer a retry (POST /changes/{id}/quizzes).
    quizzes: list[Quiz] = []
    quiz_error = None
    try:
        quizzes = _generate_change_quizzes(db, change, repository.user_id)
    except QuizError as exc:
        quiz_error = str(exc)

    return _to_response(change, quizzes, repository.local_path, quiz_error)


@router.get("/repo/{repo_id}/changes", response_model=list[AssistantResponse])
def list_changes(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[AssistantResponse]:
    """Everything the assistant has changed in this repo, newest first - so a page refresh
    (or coming back tomorrow) doesn't lose the explanations, diffs and quizzes."""
    repository = get_owned_repo(db, repo_id, user)
    changes = db.scalars(
        select(AssistantChange)
        .where(AssistantChange.repo_id == repo_id)
        .order_by(AssistantChange.created_at.desc())
        .limit(20)
    )
    return [_to_response(c, _current_quizzes(db, c.id), repository.local_path) for c in changes]


@router.post("/changes/{change_id}/quizzes", response_model=list[QuizItem])
def get_or_create_change_quizzes(
    change_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[QuizItem]:
    """The questions for a change: the existing ones, or (if generation failed earlier) a fresh
    attempt."""
    change = db.get(AssistantChange, change_id)
    if change is None or change.user_id != owner_id(user):
        raise HTTPException(status_code=404, detail="Change not found.")

    existing = _current_quizzes(db, change_id)
    if existing:
        return to_items(existing)

    repository = db.get(Repository, change.repo_id)
    try:
        rows = _generate_change_quizzes(db, change, repository.user_id if repository else change.user_id)
    except QuizError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return to_items(rows)


@router.post("/changes/{change_id}/undo", response_model=UndoResponse)
def undo_change(
    change_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> UndoResponse:
    """Put the files back exactly as they were before this change. Refuses if any of them has
    been edited since (by a later change or by hand), because restoring the old content would
    silently throw that newer work away."""
    change = db.get(AssistantChange, change_id)
    if change is None or change.user_id != owner_id(user):
        raise HTTPException(status_code=404, detail="Change not found.")
    repository = db.get(Repository, change.repo_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    if change.reverted:
        raise HTTPException(status_code=409, detail="This change has already been undone.")
    if not change.snapshot_json:
        raise HTTPException(status_code=409, detail="This change was made by an older version and can't be undone automatically.")

    snapshot: dict[str, dict] = json.loads(change.snapshot_json)
    root = Path(repository.local_path).resolve()
    modified = []
    for rel, snap in snapshot.items():
        current = _on_disk(repository.local_path, rel)
        if current is None or _sha(current) != snap["after_sha"]:
            modified.append(rel)
    if modified:
        raise HTTPException(
            status_code=409,
            detail="Can't undo safely: " + ", ".join(modified) + " changed again after this edit. Undo the newer change first.",
        )

    restored = []
    for rel, snap in snapshot.items():
        target = (root / rel).resolve()
        if root not in target.parents:  # stored by us, but never trust a path blindly
            continue
        if snap["before"] is None:
            target.unlink(missing_ok=True)
        else:
            newline = "\r\n" if b"\r\n" in target.read_bytes() else "\n"
            target.write_text(snap["before"], encoding="utf-8", newline=newline)
        restored.append(rel)

    commit_sha = commit_changes(repository.local_path, f"CodeLiteracy: undo “{change.summary}”", restored)
    change.reverted = True
    _refresh_repo_caches(repository)
    db.commit()
    return UndoResponse(change_id=change.id, reverted=True, restored=restored, commit_sha=commit_sha)

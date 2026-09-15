import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AssistantChange, Repository
from app.schemas import AssistantRequest, AssistantResponse
from app.services.assistant_service import AssistantError, run_assistant
from app.services.github_service import commit_changes

router = APIRouter(prefix="/api/repo", tags=["assistant"])


@router.post("/{repo_id}/assistant", response_model=AssistantResponse)
def ask_assistant(repo_id: str, payload: AssistantRequest, db: Session = Depends(get_db)) -> AssistantResponse:
    """FR5 + FR6 + FR7: request a fix/feature, have the assistant carry it out and
    explain each step, then commit the result so it's tracked like any other change."""
    repository = db.get(Repository, repo_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    try:
        result = run_assistant(repository.local_path, payload.message.strip())
    except AssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    commit_sha = commit_changes(repository.local_path, f"CodeLiteracy: {result['summary']}")

    change = AssistantChange(
        repo_id=repo_id,
        request=payload.message.strip(),
        summary=result["summary"],
        concept=result["concept"],
        steps_json=json.dumps(result["steps"]),
        files_changed_json=json.dumps(result["files_changed"]),
        commit_sha=commit_sha,
    )
    db.add(change)
    db.commit()
    db.refresh(change)

    return AssistantResponse(
        change_id=change.id,
        summary=change.summary,
        concept=change.concept,
        steps=result["steps"],
        files_changed=result["files_changed"],
        commit_sha=commit_sha,
    )

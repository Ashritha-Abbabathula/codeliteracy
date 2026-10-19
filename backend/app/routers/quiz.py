"""Server-verified quizzes. Answers are checked here, the notebook is credited here (only for
a genuinely correct answer, once per question), and the correct answer is only ever revealed
in the response to a submitted answer.

Teaching flow: a learner gets two tries at a question. A first wrong answer returns *why that
option is wrong* and a hint, and keeps the answer hidden so the second try is still thinking,
not clicking. A second wrong answer reveals the answer with its explanation and something to
read (FR9), and the learner can ask for a fresh question on the same concept (FR10)."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_optional, owner_id
from app.models import AssistantChange, NotebookEntry, Quiz, Repository, User
from app.schemas import QuizAnswerRequest, QuizAnswerResponse, QuizItem, ResourceRecommendation
from app.services.diff_utils import diff_excerpt
from app.services.quiz_service import QuizError, generate_fresh_question
from app.services.quiz_store import (
    MAX_ATTEMPTS,
    final_review,
    is_closed,
    new_quiz_row,
    option_note,
    stored_resource,
    to_item,
)
from app.services.repo_context import numbered_excerpt
from app.services.resource_service import ResourceError, recommend_resource

router = APIRouter(prefix="/api", tags=["quiz"])


def _owned_quiz(db: Session, quiz_id: str, user: User | None) -> Quiz:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or quiz.user_id != owner_id(user):
        raise HTTPException(status_code=404, detail="Quiz not found.")
    return quiz


def _save_to_notebook(db: Session, quiz: Quiz) -> bool:
    """Credit the notebook for a correct answer. Idempotent per quiz. Returns True if a new
    entry was created."""
    if db.scalar(select(NotebookEntry).where(NotebookEntry.quiz_id == quiz.id)) is not None:
        return False

    repo_name = "Connected repo"
    summary = quiz.explanation or "Concept validated via multiple choice quiz."
    category = "file_walkthrough"
    file_path = quiz.file_path

    if quiz.change_id:
        category = "change"
        change = db.get(AssistantChange, quiz.change_id)
        if change:
            summary = change.summary
            if quiz.explanation:
                summary += f"\n\nWhat the question checked: {quiz.explanation}"
            files = json.loads(change.files_changed_json or "[]")
            file_path = file_path or (files[0] if files else None)
    repo = db.get(Repository, quiz.repo_id) if quiz.repo_id else None
    if repo:
        repo_name = repo.name

    db.add(NotebookEntry(
        user_id=quiz.user_id, quiz_id=quiz.id, concept=quiz.concept, question=quiz.question,
        summary=summary, repo_name=repo_name, file_path=file_path, category=category,
    ))
    db.commit()
    return True


def _resource_for(quiz: Quiz) -> ResourceRecommendation | None:
    """What to read after a miss: the one written with the question, else ask for one now."""
    stored = stored_resource(quiz)
    if stored:
        return stored
    try:
        return ResourceRecommendation(**recommend_resource(quiz.concept, quiz.question))
    except ResourceError:
        return None  # the wrong-answer feedback itself must not depend on this extra


@router.post("/quiz/{quiz_id}/answer", response_model=QuizAnswerResponse)
def answer_quiz(
    quiz_id: str,
    payload: QuizAnswerRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> QuizAnswerResponse:
    quiz = _owned_quiz(db, quiz_id, user)
    options = json.loads(quiz.options_json)
    choice = payload.selected_index
    if not 0 <= choice < len(options):
        raise HTTPException(status_code=400, detail="That isn't one of the answer options.")

    # Already closed: report what happened, change nothing. (Its answer has been revealed, so
    # a late "correct" click must never earn notebook credit.)
    if is_closed(quiz):
        return final_review(quiz)

    if quiz.attempts == 1 and choice == quiz.first_choice:
        raise HTTPException(status_code=400, detail="You've already tried that option. Pick a different one.")

    quiz.attempts = (quiz.attempts or 0) + 1
    quiz.last_choice = choice
    correct = choice == quiz.correct_index

    if correct:
        quiz.solved = True
        db.commit()
        saved = _save_to_notebook(db, quiz)
        return final_review(quiz, saved=saved)

    if quiz.attempts < MAX_ATTEMPTS:
        quiz.first_choice = choice
        db.commit()
        return QuizAnswerResponse(
            correct=False, final=False, selected_index=choice, correct_index=None,
            option_feedback=option_note(quiz, choice), hint=quiz.hint,
            attempts_left=MAX_ATTEMPTS - quiz.attempts,
        )

    db.commit()
    return final_review(quiz, resource=_resource_for(quiz))


def _retry_context(db: Session, previous: Quiz) -> str:
    """The real code the concept came from, so a fresh question is as grounded as the first."""
    parts: list[str] = []
    if previous.change_id:
        change = db.get(AssistantChange, previous.change_id)
        if change:
            steps = "\n".join(
                f"- {s.get('action', '')}: {s.get('explanation', '')}" for s in json.loads(change.steps_json or "[]")
            )
            parts.append(f"The code change being studied: {change.summary}\nSteps and rationale:\n{steps}")
            excerpt = diff_excerpt(json.loads(change.diff_json or "[]"), limit=5000)
            if excerpt:
                parts.append(f"The actual code changes (- removed, + added):\n{excerpt}")
    repo = db.get(Repository, previous.repo_id) if previous.repo_id else None
    if repo and previous.file_path and not previous.change_id:
        excerpt = numbered_excerpt(repo.local_path, previous.file_path, max_lines=260)
        if excerpt:
            parts.append(f"File being studied: {previous.file_path}\nSource (with line numbers):\n{excerpt[0]}")
    elif previous.file_path:
        parts.append(f"File: {previous.file_path}")
    return "\n\n".join(parts)


@router.post("/quiz/{quiz_id}/retry", response_model=QuizItem)
def retry_quiz(
    quiz_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> QuizItem:
    """After reviewing the resource/discussion: a fresh question on the same concept (the old
    one's answer has already been revealed, so re-asking it would prove nothing)."""
    previous = _owned_quiz(db, quiz_id, user)

    siblings = select(Quiz.question).where(Quiz.concept == previous.concept, Quiz.repo_id == previous.repo_id)
    if previous.change_id:
        siblings = siblings.where(Quiz.change_id == previous.change_id)
    else:
        siblings = siblings.where(Quiz.file_path == previous.file_path)
    asked = list(dict.fromkeys([previous.question, *db.scalars(siblings.limit(6))]))

    try:
        fresh = generate_fresh_question(previous.concept, _retry_context(db, previous), avoid=asked)
    except QuizError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    fresh["concept"] = previous.concept  # same concept, so notebook/history stay coherent

    row = new_quiz_row(
        fresh, user_id=previous.user_id, repo_id=previous.repo_id,
        file_path=previous.file_path, change_id=previous.change_id,
    )
    db.add(row)
    db.flush()
    previous.replaced_by = row.id  # the new question takes the old one's place in lists

    # A file's walkthrough remembers which questions belong to it; keep that pointing at the
    # question the learner is now working on.
    if repo_row := (db.get(Repository, previous.repo_id) if previous.repo_id else None):
        cache = json.loads(repo_row.file_details_json or "{}")
        entry = cache.get(previous.file_path or "")
        if isinstance(entry, dict) and previous.id in entry.get("quiz_ids", []):
            entry["quiz_ids"] = [row.id if qid == previous.id else qid for qid in entry["quiz_ids"]]
            repo_row.file_details_json = json.dumps(cache)
    db.commit()
    db.refresh(row)
    return to_item(row)

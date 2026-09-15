import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AssistantChange, Quiz
from app.schemas import QuizAnswerRequest, QuizAnswerResponse, QuizPublic
from app.services.quiz_service import QuizError, generate_quiz
from app.services.resource_service import ResourceError, recommend_resource

router = APIRouter(prefix="/api", tags=["quiz"])


def _to_public(quiz: Quiz) -> QuizPublic:
    return QuizPublic(
        quiz_id=quiz.id,
        concept=quiz.concept,
        question=quiz.question,
        options=json.loads(quiz.options_json),
    )


def _latest_quiz(db: Session, change_id: str) -> Quiz | None:
    return db.scalar(
        select(Quiz).where(Quiz.change_id == change_id).order_by(Quiz.created_at.desc()).limit(1)
    )


def _generate_for_change(db: Session, change: AssistantChange) -> Quiz:
    try:
        generated = generate_quiz(change.concept, change.summary, json.loads(change.steps_json))
    except QuizError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    quiz = Quiz(
        change_id=change.id,
        concept=change.concept,
        question=generated["question"],
        options_json=json.dumps(generated["options"]),
        correct_index=generated["correct_index"],
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return quiz


@router.post("/changes/{change_id}/quiz", response_model=QuizPublic)
def get_or_create_quiz(change_id: str, db: Session = Depends(get_db)) -> QuizPublic:
    """FR8: generate a quiz for the concept behind this change (cached after the
    first call, same as explanations)."""
    existing = _latest_quiz(db, change_id)
    if existing is not None:
        return _to_public(existing)

    change = db.get(AssistantChange, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found.")

    return _to_public(_generate_for_change(db, change))


@router.post("/quiz/{quiz_id}/answer", response_model=QuizAnswerResponse)
def answer_quiz(quiz_id: str, payload: QuizAnswerRequest, db: Session = Depends(get_db)) -> QuizAnswerResponse:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    correct = payload.selected_index == quiz.correct_index
    resource = None
    if not correct:
        try:
            recommended = recommend_resource(quiz.concept, quiz.question)
            resource = {
                "title": recommended["title"],
                "description": recommended["description"],
                "url": recommended["url"],
            }
        except ResourceError:
            # Don't fail the whole answer just because the resource suggestion
            # couldn't be generated - the user still gets correct/incorrect feedback.
            resource = None

    return QuizAnswerResponse(correct=correct, correct_index=quiz.correct_index, resource=resource)


@router.post("/quiz/{quiz_id}/retry", response_model=QuizPublic)
def retry_quiz(quiz_id: str, db: Session = Depends(get_db)) -> QuizPublic:
    """FR10: after reviewing the resource, generate a fresh question on the same
    concept - retaking the exact same question would be trivial once the correct
    answer has already been revealed once."""
    previous = db.get(Quiz, quiz_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    change = db.get(AssistantChange, previous.change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="The change behind this quiz no longer exists.")

    return _to_public(_generate_for_change(db, change))

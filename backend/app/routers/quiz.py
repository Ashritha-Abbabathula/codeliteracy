import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AssistantChange, Quiz
from app.schemas import QuizAnswerRequest, QuizAnswerResponse, QuizPublic
from app.services.quiz_service import QuizError, generate_quiz

router = APIRouter(prefix="/api", tags=["quiz"])


def _to_public(quiz: Quiz) -> QuizPublic:
    return QuizPublic(
        quiz_id=quiz.id,
        concept=quiz.concept,
        question=quiz.question,
        options=json.loads(quiz.options_json),
    )


@router.post("/changes/{change_id}/quiz", response_model=QuizPublic)
def get_or_create_quiz(change_id: str, db: Session = Depends(get_db)) -> QuizPublic:
    """FR8: generate a quiz for the concept behind this change (cached after the
    first call, same as explanations)."""
    existing = db.scalar(select(Quiz).where(Quiz.change_id == change_id))
    if existing is not None:
        return _to_public(existing)

    change = db.get(AssistantChange, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found.")

    try:
        generated = generate_quiz(change.concept, change.summary, json.loads(change.steps_json))
    except QuizError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    quiz = Quiz(
        change_id=change_id,
        concept=change.concept,
        question=generated["question"],
        options_json=json.dumps(generated["options"]),
        correct_index=generated["correct_index"],
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return _to_public(quiz)


@router.post("/quiz/{quiz_id}/answer", response_model=QuizAnswerResponse)
def answer_quiz(quiz_id: str, payload: QuizAnswerRequest, db: Session = Depends(get_db)) -> QuizAnswerResponse:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    return QuizAnswerResponse(
        correct=payload.selected_index == quiz.correct_index,
        correct_index=quiz.correct_index,
    )

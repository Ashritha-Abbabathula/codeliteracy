"""Turning generated questions into stored rows, and stored rows into what a learner may see."""

import json
from typing import Any

from app.models import Quiz
from app.schemas import QuizAnswerResponse, QuizItem, ResourceRecommendation

MAX_ATTEMPTS = 2


def new_quiz_row(q: dict[str, Any], *, user_id: str | None, repo_id: str | None,
                 file_path: str | None = None, change_id: str | None = None) -> Quiz:
    return Quiz(
        user_id=user_id, repo_id=repo_id, file_path=file_path, change_id=change_id,
        concept=q["concept"], question=q["question"],
        options_json=json.dumps(q["options"]), correct_index=q["correct_index"],
        explanation=q.get("explanation"), hint=q.get("hint"),
        option_notes_json=json.dumps(q["option_notes"]) if q.get("option_notes") else None,
        resource_json=json.dumps(q["resource"]) if q.get("resource") else None,
    )


def is_closed(quiz: Quiz) -> bool:
    return bool(quiz.solved) or (quiz.attempts or 0) >= MAX_ATTEMPTS


def option_note(quiz: Quiz, index: int | None) -> str | None:
    if index is None or not quiz.option_notes_json:
        return None
    notes = json.loads(quiz.option_notes_json)
    return notes[index] if 0 <= index < len(notes) else None


def stored_resource(quiz: Quiz) -> ResourceRecommendation | None:
    return ResourceRecommendation(**json.loads(quiz.resource_json)) if quiz.resource_json else None


def final_review(quiz: Quiz, *, saved: bool = False, resource: ResourceRecommendation | None = None) -> QuizAnswerResponse:
    """Everything revealed: only for a question that is closed."""
    return QuizAnswerResponse(
        correct=bool(quiz.solved), final=True, selected_index=quiz.last_choice,
        correct_index=quiz.correct_index, explanation=quiz.explanation,
        option_feedback=option_note(quiz, quiz.last_choice),
        resource=None if quiz.solved else (resource or stored_resource(quiz)),
        saved_to_notebook=saved, attempts_left=0,
    )


def to_item(quiz: Quiz) -> QuizItem:
    closed = is_closed(quiz)
    one_wrong = not closed and (quiz.attempts or 0) == 1 and quiz.first_choice is not None
    return QuizItem(
        id=quiz.id, concept=quiz.concept, question=quiz.question,
        options=json.loads(quiz.options_json),
        attempts=quiz.attempts or 0,
        eliminated=[quiz.first_choice] if one_wrong else [],
        hint=quiz.hint if one_wrong else None,
        review=final_review(quiz) if closed else None,
    )


def to_items(quizzes: list[Quiz]) -> list[QuizItem]:
    return [to_item(q) for q in quizzes]

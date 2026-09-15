"""FR8: once a fix or feature is finished, generate a short quiz targeting the concept
the user was just exposed to."""

import json

from app.services.llm_client import LLMCallError, LLMNotConfiguredError, json_completion

_SYSTEM_PROMPT = """\
You are CodeLiteracy's quiz engine. A developer just had the assistant make a code \
change for them, and you need to check whether they actually understood the concept \
behind it, not just watched it happen. Write exactly one multiple-choice question that \
tests understanding of the concept (not memorization of exact variable/file names from \
the change). Respond with strict JSON only, matching exactly:

{"question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0}

Exactly 4 options, plausible distractors, correct_index is the 0-based index of the \
right answer. Do not wrap the JSON in markdown fences."""


class QuizError(Exception):
    pass


def generate_quiz(concept: str, change_summary: str, steps: list[dict]) -> dict:
    steps_text = "\n".join(f"- {s['action']}: {s['explanation']}" for s in steps)
    user_prompt = (
        f"Concept to quiz: {concept}\n\n"
        f"What the assistant just did:\n{change_summary}\n\n"
        f"Steps taken:\n{steps_text or '(none recorded)'}"
    )

    try:
        raw_text = json_completion(_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
    except (LLMNotConfiguredError, LLMCallError) as exc:
        raise QuizError(str(exc)) from exc

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise QuizError("The quiz LLM returned a response that wasn't valid JSON.") from exc

    if (
        "question" not in parsed
        or "options" not in parsed
        or "correct_index" not in parsed
        or len(parsed["options"]) != 4
        or not (0 <= parsed["correct_index"] < 4)
    ):
        raise QuizError("The quiz LLM response didn't match the expected shape.")
    return parsed

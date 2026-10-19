"""Quiz generation: 3-4 multiple-choice questions after an assistant change or a file
walkthrough. If the AI can't produce real questions this raises QuizError - it never
substitutes canned filler questions, because a quiz that isn't about the learner's actual
code (and that credits a "mastered" notebook entry) is worse than no quiz.

Each question comes with the material needed to *teach* from a wrong answer, generated in the
same call (so answering is instant and costs no extra quota): a hint that doesn't give the
answer away, a reason for every option, and what to read up on."""

import random
from typing import Any
from urllib.parse import quote_plus

from app.services.llm_client import LLMCallError, LLMNotConfiguredError, json_object

_QUIZ_SYSTEM_PROMPT = """\
You are CodeLiteracy's quiz engine. A developer just worked with some real code and you \
must check they actually understood it - the reasoning, not surface trivia.

Write {count} multiple-choice questions grounded in the specific code/changes provided.

What makes a good question here:
- It can only be answered by understanding THIS code: refer to its real function, class and \
variable names, and quote a short line when that helps.
- It tests behaviour and reasoning: what happens for a given input, why a check or design \
choice is there, what would break if a line were removed, how two pieces interact.
- Mix the kinds: at least one "what happens if / what does this return" question and at least \
one "why is it written this way" question. Each question covers a different idea.
- All four options are the same kind of thing, similar in length, and each wrong option is a \
mistake a real learner would make. Never use "all of the above" / "none of the above".
- The answer must be verifiable from the code shown. Do not ask about anything not shown.
- No syntax trivia, no "which library is imported", no questions about line numbers or \
about what a name is called.

Respond with strict JSON only, matching exactly:
{{"quizzes": [{{"concept": "short concept name (2-5 words)",
  "question": "...",
  "options": ["...", "...", "...", "..."],
  "correct_index": 0,
  "option_explanations": ["one sentence on why option 0 is right or wrong", "... option 1", "... option 2", "... option 3"],
  "hint": "a nudge that points at where in the code to look or what to think about, WITHOUT revealing the answer or naming an option",
  "explanation": "2-3 sentences teaching the idea: why the correct option is right, in terms of the code",
  "search_query": "a web search query a beginner could use to learn this concept in general"}}]}}

Rules: exactly 4 options each; correct_index is the 0-based index of the right answer; \
option_explanations has exactly 4 entries in the same order as options. Write for someone \
still learning: plain words, short sentences. Do not wrap the JSON in markdown fences."""


class QuizError(Exception):
    pass


def _text(value: Any, limit: int = 1200) -> str | None:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def clean_quiz(raw: Any) -> dict[str, Any] | None:
    """Validate one model-produced question and randomize where the right answer sits."""
    if not isinstance(raw, dict):
        return None
    question = raw.get("question")
    options = raw.get("options")
    correct = raw.get("correct_index")
    if not isinstance(question, str) or not question.strip():
        return None
    if not isinstance(options, list) or len(options) != 4 or not all(isinstance(o, str) and o.strip() for o in options):
        return None
    if len({o.strip().lower() for o in options}) != 4:
        return None
    if not isinstance(correct, int) or isinstance(correct, bool) or not 0 <= correct < 4:
        return None

    notes = raw.get("option_explanations")
    if not (isinstance(notes, list) and len(notes) == 4 and all(isinstance(n, str) and n.strip() for n in notes)):
        notes = None  # optional: older/partial responses still make a valid question

    order = list(range(4))
    random.shuffle(order)  # models overwhelmingly put the correct answer first
    concept = str(raw.get("concept") or "Code comprehension").strip()[:200]
    query = _text(raw.get("search_query"), 200)
    return {
        "concept": concept,
        "question": question.strip(),
        "options": [options[i].strip() for i in order],
        "correct_index": order.index(correct),
        "explanation": _text(raw.get("explanation")),
        "hint": _text(raw.get("hint"), 400),
        "option_notes": [notes[i].strip() for i in order] if notes else None,
        "resource": build_resource(concept, query) if query else None,
    }


def build_resource(concept: str, search_query: str, description: str | None = None) -> dict[str, str]:
    """FR9. We build the link ourselves (a search) rather than trusting a model-written URL,
    which can point nowhere."""
    return {
        "title": f"Read up on: {concept}",
        "description": description or f"A quick search to learn the idea behind this question: “{search_query}”.",
        "url": f"https://www.google.com/search?q={quote_plus(search_query)}",
    }


def _generate(context: str, count: int) -> list[dict[str, Any]]:
    try:
        parsed = json_object(_QUIZ_SYSTEM_PROMPT.format(count=count), context, max_tokens=4000)
    except (LLMNotConfiguredError, LLMCallError) as exc:
        raise QuizError(str(exc)) from exc

    raw_list = parsed.get("quizzes")
    if not isinstance(raw_list, list):
        raise QuizError("The AI didn't return any quiz questions. Please try again.")
    quizzes = [q for q in (clean_quiz(item) for item in raw_list) if q]
    if len(quizzes) < min(2, count):
        raise QuizError("The AI's quiz questions were malformed. Please try again.")
    return quizzes[:4]


def generate_quizzes_for_change(
    concept: str, change_summary: str, steps: list[dict], code_excerpt: str = ""
) -> list[dict[str, Any]]:
    steps_text = "\n".join(f"- {s.get('action', '')}: {s.get('explanation', '')}" for s in steps)
    context = (
        f"Concept the change illustrates: {concept}\n\n"
        f"What was changed:\n{change_summary}\n\n"
        f"Steps taken and rationale:\n{steps_text or '(none recorded)'}"
    )
    if code_excerpt:
        context += (
            "\n\nThe actual code changes (lines starting with - were removed, + were added):\n"
            f"{code_excerpt[:6000]}"
        )
    context += (
        "\n\nAsk about the change itself: what the new code does differently from the old code, "
        "why that is better, and what input or situation it now handles."
    )
    return _generate(context, count=3)


def generate_quizzes_for_file(file_path: str, overview: str, numbered_source: str) -> list[dict[str, Any]]:
    context = (
        f"File: {file_path}\nWhat it does: {overview}\n\n"
        f"Source (with line numbers):\n{numbered_source[:12000]}"
    )
    return _generate(context, count=4)


def generate_fresh_question(concept: str, context: str, avoid: list[str] | None = None) -> dict[str, Any]:
    """FR10: after a wrong answer, one *new* question on the same concept (re-asking the same
    question would be pointless once its answer has been revealed). `context` carries the real
    code, so the new question is as grounded as the first; `avoid` lists questions already asked."""
    asked = "\n".join(f"- {q}" for q in (avoid or []))
    prompt = (
        f"Focus on this concept: {concept}\n\n{context}\n\n"
        "The learner got an earlier question on this concept wrong and has since read the "
        "explanation. Write ONE new question that checks the same idea from a different angle "
        "(for example a different input, or 'what would break if...'), so it can't be answered "
        "by remembering the earlier answer."
    )
    if asked:
        prompt += f"\n\nDo not repeat or lightly reword these already-asked questions:\n{asked}"
    return _generate(prompt, count=1)[0]

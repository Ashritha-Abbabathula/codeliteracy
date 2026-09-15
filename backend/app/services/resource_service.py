"""FR9: a wrong quiz answer triggers a recommended learning resource covering that
concept. The LLM picks what to look up; we build the actual link ourselves (a search
URL) rather than trusting an LLM-generated URL, which can point nowhere."""

import json
from urllib.parse import quote_plus

from app.services.llm_client import LLMCallError, LLMNotConfiguredError, json_completion

_SYSTEM_PROMPT = """\
A developer just answered a quiz question wrong. Suggest what they should read up on \
to understand the concept, in a way a total beginner to it could follow. Respond with \
strict JSON only, matching exactly:

{"title": "short, specific title for what to look up", \
"description": "1-2 sentences on what they should focus on and why it matters here", \
"search_query": "a good web search query to find a solid explanation of this"}

Do not wrap the JSON in markdown fences."""


class ResourceError(Exception):
    pass


def recommend_resource(concept: str, question: str) -> dict:
    user_prompt = f"Concept: {concept}\nQuestion they missed: {question}"

    try:
        raw_text = json_completion(_SYSTEM_PROMPT, user_prompt, max_tokens=512)
    except (LLMNotConfiguredError, LLMCallError) as exc:
        raise ResourceError(str(exc)) from exc

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ResourceError("The resource LLM returned a response that wasn't valid JSON.") from exc

    if not all(key in parsed for key in ("title", "description", "search_query")):
        raise ResourceError("The resource LLM response was missing expected fields.")

    return {
        "title": parsed["title"],
        "description": parsed["description"],
        "url": f"https://www.google.com/search?q={quote_plus(parsed['search_query'])}",
    }

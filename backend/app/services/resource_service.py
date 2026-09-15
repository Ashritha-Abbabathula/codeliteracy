"""FR9: a wrong quiz answer triggers a recommended learning resource covering that
concept. The LLM picks what to look up; we build the actual link ourselves (a search
URL) rather than trusting an LLM-generated URL, which can point nowhere."""

import json
from urllib.parse import quote_plus

from anthropic import Anthropic

from app.config import get_settings

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
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ResourceError("ANTHROPIC_API_KEY is not set. Add it to backend/.env to enable resources.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Concept: {concept}\nQuestion they missed: {question}"}],
    )
    raw_text = "".join(block.text for block in message.content if block.type == "text")

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

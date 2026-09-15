"""Thin shared wrapper around the Gemini API. Every LLM-backed service (explainer,
assistant, quiz, resource) goes through this so there's one place that knows how to
talk to Gemini, rather than four copies of the same client setup."""

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import get_settings


class LLMNotConfiguredError(Exception):
    pass


class LLMCallError(Exception):
    pass


def require_api_key() -> None:
    if not get_settings().gemini_api_key:
        raise LLMNotConfiguredError(
            "GEMINI_API_KEY is not set. Add a free key from https://aistudio.google.com/apikey "
            "to backend/.env to enable this feature."
        )


def get_client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


def json_completion(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
    """A one-shot call that returns raw JSON text. response_mime_type enforces valid
    JSON output, so callers don't need to strip markdown fences or hope the model
    followed instructions."""
    require_api_key()
    client = get_client()  # keep a strong reference: a throwaway client can be
    # garbage-collected mid-call, closing its transport before the request completes.
    try:
        response = client.models.generate_content(
            model=get_settings().llm_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
                # These are short, well-specified JSON tasks - extended thinking just
                # burns free-tier budget (SRS design constraint) without improving them.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
    except APIError as exc:
        raise LLMCallError(f"Gemini API call failed: {exc}") from exc

    if not response.text:
        raise LLMCallError("Gemini returned an empty response (it may have been safety-filtered).")
    return response.text

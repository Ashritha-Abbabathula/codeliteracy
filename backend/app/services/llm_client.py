"""Thin shared wrapper around the Gemini API. Every LLM-backed service (explainer,
assistant, quiz, chat, ...) goes through this so there's one place that knows how to
talk to Gemini, handle transient failures, and turn API errors into messages a learner
can act on."""

import json
import time
from typing import Any

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import get_settings


class LLMNotConfiguredError(Exception):
    pass


class LLMCallError(Exception):
    pass


# Transient server-side problems worth a quick retry. 429 (free-tier rate limit) gets a
# single, longer retry: the per-minute window usually clears within a few seconds.
_RETRY_DELAYS_5XX = (1.5, 4.0, 8.0)
_RETRY_DELAY_429 = 10.0


def require_api_key() -> None:
    if not get_settings().gemini_api_key:
        raise LLMNotConfiguredError(
            "GEMINI_API_KEY is not set. Add a free key from https://aistudio.google.com/apikey "
            "to backend/.env to enable this feature."
        )


def get_client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


def _friendly_error(exc: APIError) -> str:
    code = getattr(exc, "code", None)
    if code == 429:
        return "Gemini's free-tier rate limit was hit. Wait about a minute and try again."
    if code in (500, 502, 503, 504):
        return "Gemini is overloaded right now. Please try again in a moment."
    if code in (400, 401, 403):
        return f"Gemini rejected the request ({code}). Check that GEMINI_API_KEY in backend/.env is valid."
    if code == 404:
        return "The configured Gemini model is not available. Set LLM_MODEL in backend/.env to a current model."
    return f"Gemini API call failed: {exc}"


def generate_with_retry(client: genai.Client, **kwargs: Any) -> types.GenerateContentResponse:
    """client.models.generate_content with retry on transient errors. `client` must be
    kept alive by the caller for the duration of the call (a throwaway client can be
    garbage-collected mid-request, closing its transport)."""
    attempt = 0
    network_attempts = 0
    while True:
        try:
            return client.models.generate_content(**kwargs)
        except APIError as exc:
            code = getattr(exc, "code", None)
            if code == 429 and attempt == 0:
                delay = _RETRY_DELAY_429
            elif code in (500, 502, 503, 504) and attempt < len(_RETRY_DELAYS_5XX):
                delay = _RETRY_DELAYS_5XX[attempt]
            else:
                raise LLMCallError(_friendly_error(exc)) from exc
            attempt += 1
            time.sleep(delay)
        except (httpx.HTTPError, OSError) as exc:
            # No internet, DNS failure, a proxy refusing the connection, a timeout... None of
            # these are APIErrors, and letting them escape would surface as a bare HTTP 500.
            if network_attempts < 1 and isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
                network_attempts += 1
                time.sleep(_RETRY_DELAYS_5XX[0])
                continue
            raise LLMCallError(
                "Couldn't reach Gemini. Check this computer's internet connection (or proxy/firewall) and try again."
            ) from exc


def json_completion(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
    """A one-shot call that returns raw JSON text. response_mime_type enforces valid
    JSON output, so callers don't need to strip markdown fences or hope the model
    followed instructions."""
    require_api_key()
    client = get_client()
    response = generate_with_retry(
        client,
        model=get_settings().llm_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
            # These are short, well-specified JSON tasks - extended thinking just
            # burns free-tier budget without improving them.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    if not response.text:
        raise LLMCallError("Gemini returned an empty response (it may have been safety-filtered).")
    return response.text


def json_object(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict[str, Any]:
    """json_completion + parsing. Retries once if the model returns malformed JSON (rare in
    JSON mode, but it happens when output is truncated at max_tokens)."""
    last_error: Exception | None = None
    for _ in range(2):
        raw = json_completion(system_prompt, user_prompt, max_tokens=max_tokens)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
        last_error = ValueError("expected a JSON object")
    raise LLMCallError("The AI returned a malformed response. Please try again.") from last_error

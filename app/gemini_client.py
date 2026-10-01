"""Thin wrapper over google-genai. JSON-schema output, retry with backoff.

Only this module talks to the Gemini API. Callers pass already PII-stripped
text; nothing here decides what to send — see scoring.py / brief.py /
email_draft.py for the prompts, and pii.py for what gets stripped first.
"""
from __future__ import annotations

import logging
import random
import time

from google import genai
from google.genai import errors, types

from app.config import settings

logger = logging.getLogger("kargo.gemini")

RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BASE_DELAY_SECONDS = 1.5

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def generate_json(
    *,
    system_instruction: str,
    user_content: str,
    response_schema: dict,
    temperature: float,
) -> dict:
    """Calls Gemini in JSON mode and returns the parsed response dict.

    Retries with exponential backoff + jitter on rate-limit / transient
    server errors. Raises on anything else, or after exhausting retries.
    """
    if not settings.gemini_model:
        raise RuntimeError("GEMINI_MODEL is not set")

    client = get_client()
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_json_schema=response_schema,
        temperature=temperature,
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=user_content,
                config=config,
            )
            return _parse_json_response(response)
        except errors.APIError as exc:
            last_error = exc
            code = getattr(exc, "code", None)
            if code not in RETRYABLE_CODES or attempt == MAX_RETRIES:
                raise
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning("Gemini call failed (code=%s), retry %d/%d in %.1fs", code, attempt, MAX_RETRIES, delay)
            time.sleep(delay)
    raise last_error or RuntimeError("Gemini call failed with no response")


def _parse_json_response(response) -> dict:
    import json

    text = response.text
    if not text:
        raise ValueError("Gemini returned an empty response")
    return json.loads(text)

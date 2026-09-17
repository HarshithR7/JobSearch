"""Thin wrapper around the Anthropic SDK so the rest of analysis/ never
touches the client directly — keeps provider swaps (and testing/mocking)
to one place."""

import json

import anthropic

from config import settings, logger


class AIUnavailableError(RuntimeError):
    pass


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if not settings.ANTHROPIC_API_KEY:
        raise AIUnavailableError("ANTHROPIC_API_KEY is not set — add it to .env before using AI features.")
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def complete_json(system: str, user: str, max_tokens: int = 2000, model: str | None = None) -> dict:
    """Sends one message, asks for a strict JSON object back, and parses it.
    Raises AIUnavailableError if no key is configured, or json.JSONDecodeError
    if the model didn't return valid JSON (callers should let that surface —
    silently guessing at malformed output risks fabricated data).
    model overrides settings.ANTHROPIC_MODEL — used by job_matcher.score_job
    to route high-volume scoring calls to the cheaper ANTHROPIC_MODEL_FAST
    tier instead of the default."""
    client = _get_client()
    response = client.messages.create(
        model=model or settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    logger.debug(f"AI response ({len(text)} chars): {text[:200]}...")
    return json.loads(text.strip())

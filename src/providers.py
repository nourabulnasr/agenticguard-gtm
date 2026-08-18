"""
Provider abstraction — the ONLY module that knows how to talk to Groq,
Gemini, or Anthropic. Every other module calls call_cheap()/call_quality()
and never imports a provider SDK directly. This is what makes
config.PROVIDER_MODE a one-line swap: flip it, and every caller in the
codebase is unaffected.
"""
import logging
import time
from dataclasses import dataclass
from typing import Literal

from . import config

logger = logging.getLogger(__name__)

# Infra-level retry for transient provider errors (rate limit, 5xx,
# connection reset) — distinct from the anti-hallucination "retry once on
# parse failure" logic in reply_classifier/discovery/drafting. This one
# retries the same request unchanged; that one retries with the model
# having produced bad output. Non-transient errors (400s, auth) are not
# retried and propagate immediately.
_TRANSIENT_MAX_RETRIES = 2
_TRANSIENT_BACKOFF_SECONDS = 3
_TRANSIENT_MARKERS = ("503", "429", "500", "502", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "Connection")


def _with_transient_retry(call_fn):
    for attempt in range(_TRANSIENT_MAX_RETRIES + 1):
        try:
            return call_fn()
        except Exception as e:
            is_transient = any(marker in str(e) for marker in _TRANSIENT_MARKERS)
            if not is_transient or attempt == _TRANSIENT_MAX_RETRIES:
                raise
            logger.warning(
                "transient provider error (attempt %d/%d): %s — retrying in %ds",
                attempt + 1,
                _TRANSIENT_MAX_RETRIES,
                e,
                _TRANSIENT_BACKOFF_SECONDS,
            )
            time.sleep(_TRANSIENT_BACKOFF_SECONDS)


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    role: Literal["cheap", "quality"]


def _call_groq(system: str, user: str, json_mode: bool, max_tokens: int) -> LLMResult:
    from groq import Groq

    client = Groq(api_key=config.GROQ_API_KEY)
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        # gpt-oss models on Groq are reasoning models; low effort keeps
        # this cheap-role call fast and keeps the reasoning trace out of
        # the returned text (matches the "cheap, mechanical" routing intent).
        reasoning_effort="low",
        **kwargs,
    )
    usage = resp.usage
    return LLMResult(
        text=resp.choices[0].message.content or "",
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        model=config.GROQ_MODEL,
        role="cheap",
    )


def _call_gemini(system: str, user: str, json_mode: bool, max_tokens: int) -> LLMResult:
    from google import genai
    from google.genai import types

    # Explicit timeout: the default client timeout is too short for a
    # thinking-capable model under load and raises DEADLINE_EXCEEDED
    # before the transient-retry wrapper even gets a chance to fire.
    client = genai.Client(
        api_key=config.GOOGLE_API_KEY, http_options=types.HttpOptions(timeout=45000)
    )
    cfg_kwargs = {
        "system_instruction": system,
        "max_output_tokens": max_tokens,
    }
    if json_mode:
        cfg_kwargs["response_mime_type"] = "application/json"
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=user,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    usage = resp.usage_metadata
    return LLMResult(
        text=resp.text or "",
        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
        output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        model=config.GEMINI_MODEL,
        role="quality",
    )


def _call_anthropic(
    system: str, user: str, model: str, role: Literal["cheap", "quality"], max_tokens: int
) -> LLMResult:
    from anthropic import Anthropic

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content if hasattr(block, "text"))
    return LLMResult(
        text=text,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        model=model,
        role=role,
    )


def call_cheap(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 800) -> LLMResult:
    """Route a call through the 'cheap' role: mechanical, high-volume work
    (scraping/parsing, risk classification, reply classification). Free
    tier -> Groq; PROVIDER_MODE="anthropic" -> Claude Haiku 4.5."""
    if config.CHEAP_PROVIDER == "groq":
        result = _with_transient_retry(lambda: _call_groq(system, user, json_mode, max_tokens))
    else:
        result = _with_transient_retry(
            lambda: _call_anthropic(system, user, config.CHEAP_MODEL, "cheap", max_tokens)
        )
    from . import cost_tracker

    cost_tracker.TRACKER.record(result)
    return result


def call_quality(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 800) -> LLMResult:
    """Route a call through the 'quality' role: persuasive drafting. Free
    tier -> Gemini; PROVIDER_MODE="anthropic" -> Claude Sonnet 5."""
    if config.QUALITY_PROVIDER == "gemini":
        result = _with_transient_retry(lambda: _call_gemini(system, user, json_mode, max_tokens))
    else:
        result = _with_transient_retry(
            lambda: _call_anthropic(system, user, config.QUALITY_MODEL, "quality", max_tokens)
        )
    from . import cost_tracker

    cost_tracker.TRACKER.record(result)
    return result

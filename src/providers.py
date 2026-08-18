"""
Provider abstraction — the ONLY module that knows how to talk to Groq,
Gemini, or Anthropic. Every other module calls call_cheap()/call_quality()
and never imports a provider SDK directly. This is what makes
config.PROVIDER_MODE a one-line swap: flip it, and every caller in the
codebase is unaffected.
"""
from dataclasses import dataclass
from typing import Literal

from . import config


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

    client = genai.Client(api_key=config.GOOGLE_API_KEY)
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
        result = _call_groq(system, user, json_mode, max_tokens)
    else:
        result = _call_anthropic(system, user, config.CHEAP_MODEL, "cheap", max_tokens)
    from . import cost_tracker

    cost_tracker.TRACKER.record(result)
    return result


def call_quality(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 800) -> LLMResult:
    """Route a call through the 'quality' role: persuasive drafting. Free
    tier -> Gemini; PROVIDER_MODE="anthropic" -> Claude Sonnet 5."""
    if config.QUALITY_PROVIDER == "gemini":
        result = _call_gemini(system, user, json_mode, max_tokens)
    else:
        result = _call_anthropic(system, user, config.QUALITY_MODEL, "quality", max_tokens)
    from . import cost_tracker

    cost_tracker.TRACKER.record(result)
    return result

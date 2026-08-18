"""
Single source of truth for which LLM providers back the "cheap" and
"quality" routing roles, plus the pricing table used to PROJECT cost
against the production target architecture (Claude Haiku 4.5 / Sonnet 5),
regardless of which free-tier model actually served a given PoC call.

Swap PROVIDER_MODE to "anthropic" to point both roles directly at Claude.
That one line is the entire migration path back to the brief's target stack.
"""
import os
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# THE SINGLE SWAPPABLE LINE
# ============================================================
PROVIDER_MODE: Literal["free_tier", "anthropic"] = "free_tier"

# --- Free-tier PoC models (zero cost, no card) ---
# NOTE: the brief named "llama-3.3-70b-versatile" for this role. Verified
# live against this Groq key (2026-08-18, client.models.list()) that it has
# since been retired from Groq's catalog — 404 model_not_found. Swapped to
# openai/gpt-oss-20b, a small/fast open-weight model on Groq that fills the
# same "cheap, mechanical" role; call sites set reasoning_effort="low" to
# keep it fast and keep its (Groq-specific) reasoning trace out of the
# returned JSON text. If your key has llama-3.3-70b-versatile access,
# swap it back — nothing else in the codebase depends on the model name.
GROQ_MODEL = "openai/gpt-oss-20b"  # stands in for Claude Haiku 4.5
GEMINI_MODEL = "gemini-2.5-flash"  # stands in for Claude Sonnet 5

# --- Production target models (per the brief's cost model) ---
ANTHROPIC_CHEAP_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_QUALITY_MODEL = "claude-sonnet-5"

if PROVIDER_MODE == "free_tier":
    CHEAP_PROVIDER: Literal["groq", "anthropic"] = "groq"
    QUALITY_PROVIDER: Literal["gemini", "anthropic"] = "gemini"
    CHEAP_MODEL = GROQ_MODEL
    QUALITY_MODEL = GEMINI_MODEL
else:
    CHEAP_PROVIDER = "anthropic"
    QUALITY_PROVIDER = "anthropic"
    CHEAP_MODEL = ANTHROPIC_CHEAP_MODEL
    QUALITY_MODEL = ANTHROPIC_QUALITY_MODEL

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")

# Standard (post-intro) per-1M-token USD rates, Anthropic first-party pricing,
# confirmed via the claude-api skill's live-cached model table (2026-06-24).
# Used for cost PROJECTION only — the free-tier PoC calls above cost $0.
PRICING = {
    "cheap": {
        "input_per_1m": 1.00,
        "output_per_1m": 5.00,
        "model_label": "claude-haiku-4-5",
    },
    "quality": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
        "model_label": "claude-sonnet-5",
    },
}

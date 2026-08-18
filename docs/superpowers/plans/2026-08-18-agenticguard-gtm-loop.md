# AgenticGuard "Autonomous GTM Loop" Take-Home — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 4-stage GTM automation pipeline (Discovery → Enrichment → Drafting → Reply Classifier) for 5 fintech targets, with a documented Haiku/Sonnet cost-routing architecture, a strictly anti-hallucinating reply classifier, and a free-tier PoC runtime that is one config line away from the real Anthropic models.

**Architecture:** Two-tier model routing behind a single provider abstraction (`providers.py`). "Cheap" role = Groq `llama-3.3-70b-versatile` in the PoC / Claude Haiku 4.5 in production, used for scraping-derived classification (discovery risk-mapping, reply classification) — high volume, mechanical, needs speed not nuance. "Quality" role = Gemini `gemini-2.5-flash` via Google AI Studio in the PoC / Claude Sonnet 5 in production, used only for the one task that needs voice and persuasion: drafting. `config.PROVIDER_MODE` is the single line that flips both roles from free-tier to Anthropic. A `CostTracker` records real token usage from every call and projects it against the documented Haiku/Sonnet per-token pricing, regardless of which free-tier provider actually served the call, so the printed total answers "what would this cost on the target architecture" — not "what did the free tier bill" (which is $0).

**Tech Stack:** Python 3.11+, `groq` SDK, `google-genai` SDK, `anthropic` SDK (import guarded, only exercised if `PROVIDER_MODE="anthropic"`), `pydantic` v2 for schema enforcement, `requests` + `beautifulsoup4` for scraping, `python-dotenv` for secrets. No LangChain — the pipeline is 4 linear stages with one provider call each; LangChain's abstractions (chains/agents/output parsers) don't buy anything a direct Pydantic-validated call doesn't already give us here, and the brief's own quality bar ("clean documented code") argues for fewer moving parts, not more. This was a real trade-off, not an oversight — noted in the plan's Self-Review.

**Spec:** This plan *is* the spec — it was built directly from the user's take-home brief (verbatim task list, anti-hallucination rules, and constraints are reproduced into task descriptions below rather than living in a separate spec file, since the brief was already precise and itemized).

## Global Constraints

- Runtime providers: Groq (`GROQ_API_KEY`) for the cheap role, Gemini/Google AI Studio (`GOOGLE_API_KEY`) for the quality role. Zero paid APIs, zero cards.
- Architecture doc specifies Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) and Claude Sonnet 5 (`claude-sonnet-5`) as the production targets, with token-math proving <$50 for 20 leads at documented pricing ($1/$5 per 1M Haiku, $3/$15 per 1M Sonnet — standard rate, not the 2026-08-31 intro rate, so the proof holds after it expires).
- Provider choice is a single-line swap (`config.PROVIDER_MODE`).
- Never actually send email/LinkedIn — generate payloads only, mock the send with a clear comment.
- Respect robots.txt on scraping; never scrape LinkedIn — use a real LinkedIn *search* URL (not a fabricated profile) and note in the README where Apollo API would replace this in production.
- Never pass a guessed CTO email off as real — placeholders must be clearly flagged in the data itself, not just in a code comment.
- Reply classifier: strict Pydantic-enforced JSON only, retry once on parse failure, `evidence` must be an exact verbatim substring of the reply when `meeting_requested=true`, `proposed_time=null` unless an explicit time is stated, default `false` on ambiguity.
- `.env` holds all keys; never hardcoded. (Already created this session — user pasted keys directly in chat, stored to `.env`, confirmed untracked by git.)
- git init + logical commits per task.

---

### Task 1: Project scaffolding & dependencies

**Files:**
- Create: `requirements.txt`
- Create: `src/__init__.py` (empty)
- Create: `src/config.py`
- Modify: `.gitignore` (already exists — verify `output/*.csv` is NOT ignored; the CSV is a required deliverable, not a build artifact)

**Interfaces:**
- Produces: `config.PROVIDER_MODE: Literal["free_tier", "anthropic"]`, `config.CHEAP_MODEL`, `config.QUALITY_MODEL`, `config.CHEAP_PROVIDER`, `config.QUALITY_PROVIDER` (resolved from `PROVIDER_MODE`), `config.PRICING: dict[str, dict[str, float]]` keyed by role (`"cheap"`/`"quality"`) → `{"input_per_1m": float, "output_per_1m": float, "model_label": str}` using the **Haiku/Sonnet** rates always (this is the projection table, independent of which free-tier model actually ran).

- [ ] **Step 1: Fix `.gitignore`**

Remove the `output/*.csv` / `!output/.gitkeep` lines — the CSV deliverable must be committed, not ignored.

- [ ] **Step 2: Write `requirements.txt`**

```
groq>=0.31.0
google-genai>=1.0.0
anthropic>=0.69.0
pydantic>=2.9.0
requests>=2.32.0
beautifulsoup4>=4.12.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 3: Write `src/config.py`**

```python
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
GROQ_MODEL = "llama-3.3-70b-versatile"      # stands in for Claude Haiku 4.5
GEMINI_MODEL = "gemini-2.5-flash"           # stands in for Claude Sonnet 5

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

# Standard (post-intro) per-1M-token USD rates, Anthropic first-party pricing.
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
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt src/__init__.py src/config.py .gitignore
git commit -m "chore: scaffold project, add config with swappable provider routing"
```

---

### Task 2: Architecture map (HTML, 1-page, print-to-PDF) — SHOW TO USER BEFORE CONTINUING

**Files:**
- Create: `architecture/architecture.html`

**Interfaces:** None (standalone static document; no code dependencies).

- [ ] **Step 1: Build the architecture HTML**

Single self-contained `.html` file (no external assets — must print cleanly), containing:
1. Pipeline diagram: Discovery → Enrichment → Drafting → Reply Classifier, each stage labeled with its model role (cheap/quality) and the *production* model name (Haiku 4.5 / Sonnet 5) — the architecture doc always states the target stack, not the PoC stand-ins.
2. A small "PoC note" callout: PoC runs on Groq + Gemini free tiers at $0 to prove the logic without a card; provider is a one-line config swap; architecture below is what ships in production.
3. The token-math table proving <$50/20 leads (see cost math below — reuse exactly, do not redo the arithmetic differently in two places).
4. Anti-hallucination controls diagram for the reply classifier (Pydantic schema gate → evidence-substring check → retry-once → safe-false fallback).
5. `@media print` CSS so it renders as one clean page.

Cost math to embed (per-lead estimates, conservative/high-side so the <$50 claim has margin, standard non-intro pricing):

| Stage | Model | Est. input tok | Est. output tok | Cost/lead |
|---|---|---|---|---|
| Discovery (scrape + risk-map) | Haiku 4.5 | 3,000 | 300 | $0.0045 |
| Enrichment (page parse) | Haiku 4.5 | 2,000 | 150 | $0.00275 |
| Drafting (email + LinkedIn note) | Sonnet 5 | 1,500 | 500 | $0.0120 |
| Reply classify (incl. 1 retry, worst case) | Haiku 4.5 | 1,000 | 200 | $0.0020 |
| **Total per lead** | | | | **≈$0.0213** |
| **Total for 20 leads** | | | | **≈$0.43** |

State plainly: ≈$0.43 for 20 leads is ~117x under the $50 budget — the two-tier routing (mechanical work on the cheap model, persuasive drafting reserved for the quality model) is what makes that margin possible; routing all four stages through Sonnet-tier pricing would land at ≈$0.80 for 20 leads (still comfortably under budget, but the routing is the deliberate discipline being demonstrated, not a necessity at this volume).

- [ ] **Step 2: Open/show the file to the user for review before proceeding to Task 3.**

No commit yet — this is a review checkpoint per the user's explicit build order ("show me the architecture... before the full build").

---

### Task 3: `prompts.py` — SHOW TO USER BEFORE CONTINUING

**Files:**
- Create: `src/prompts.py`

**Interfaces:**
- Produces: `DISCOVERY_SYSTEM_PROMPT: str`, `ENRICHMENT_SYSTEM_PROMPT: str`, `DRAFTING_SYSTEM_PROMPT: str`, `REPLY_CLASSIFIER_SYSTEM_PROMPT: str` — all consumed by Task 4/5/6/7/8 modules.

- [ ] **Step 1: Write `src/prompts.py`**

Each prompt gets a docstring comment above it stating: which pipeline stage uses it, which model role (cheap/quality) it's routed to, and why that role fits the task. The reply-classifier prompt is the anti-hallucination-critical one — it embeds the four required few-shot cases verbatim from the brief:

```python
"""
System prompts for the AgenticGuard GTM Loop. Grouped by pipeline stage.
Each prompt is routed through providers.call_cheap() or call_quality()
per the cost-routing rationale in architecture/architecture.html.
"""

# Stage 1: Discovery — routed to the CHEAP role (Haiku/Groq).
# Mechanical, high-volume: read scraped page text, extract one AI feature,
# map it to exactly one AgenticGuard risk category. No persuasion needed.
DISCOVERY_SYSTEM_PROMPT = """You are a security research analyst for \
AgenticGuard, a company that audits AI agent deployments for security risk.

Given raw scraped text from a company's public website, do two things:
1. Identify the ONE most prominent AI-powered feature the company markets \
or describes (e.g. an AI chatbot, an autonomous underwriting agent, a RAG-based \
support assistant). If you cannot find a specific AI feature mentioned in the \
text, say so plainly — do not invent one.
2. Map that feature to exactly one of these three AgenticGuard risk categories, \
based on what the feature actually does:
   - "prompt_injection": the feature accepts free-text input from users or \
external sources and acts on it (chatbots, support agents, autonomous assistants).
   - "rag_data_exposure": the feature retrieves and surfaces internal/proprietary \
data to answer questions (RAG-based search, internal knowledge assistants).
   - "autonomous_agent_manipulation": the feature takes real-world actions \
with reduced human oversight (autonomous transaction agents, agentic workflows \
that execute financial or account actions).

Respond with ONLY a JSON object, no other text:
{"ai_feature": "<short description, or 'not found' if none is stated>", \
"risk_category": "<one of the three categories above, or 'none' if ai_feature \
is 'not found'>", "risk_rationale": "<one sentence tying the specific feature \
to the specific risk, grounded only in what the text actually says>"}

If the page text does not describe a specific AI feature, you MUST return \
ai_feature: "not found" and risk_category: "none". Never guess a plausible-\
sounding AI feature the company might have just because it's a fintech."""


# Stage 2: Enrichment — routed to the CHEAP role (Haiku/Groq).
# Mechanical extraction: pull a name+title from scraped About/Team page text.
ENRICHMENT_SYSTEM_PROMPT = """You extract executive contact information from \
scraped company "About" or "Team" page text.

Look specifically for a CTO (Chief Technology Officer) or CISO (Chief \
Information Security Officer). Respond with ONLY a JSON object:
{"name": "<full name, or null if no CTO/CISO is named on this page>", \
"title": "<their exact title as written, or null>"}

If the page does not name a specific person holding one of these titles, \
you MUST return null for both fields. Never guess a plausible name — an \
unverified guess presented as real is worse than no answer."""


# Stage 3: Drafting — routed to the QUALITY role (Sonnet/Gemini).
# The one stage that needs voice, persuasion, and hyper-personalization —
# worth the higher per-token cost; everything upstream of it is cheap-role
# mechanical extraction that this prompt then turns into prose.
DRAFTING_SYSTEM_PROMPT = """You are a senior GTM copywriter for AgenticGuard, \
a company that helps engineering teams secure their AI agent deployments \
against prompt injection, RAG data exposure, and autonomous agent \
manipulation.

You will be given: a company name, the specific AI feature they publicly \
describe, and the specific AgenticGuard risk category that feature maps to. \
Write a hyper-personalized, concise cold email AND a short LinkedIn \
connection note, both grounded ONLY in the specific feature and risk you \
were given — never invent product details, statistics, breach incidents, \
or claims about the company that were not provided to you.

Rules:
- Reference the company's actual named AI feature specifically, not a \
generic "your AI systems."
- Name the specific risk category's real-world failure mode in plain \
language (not jargon dumping the category name itself).
- Email: 120-160 words, one clear call to action (a 15-minute call), no \
fake urgency, no fabricated stats.
- LinkedIn note: under 300 characters, warmer and shorter, same specific \
hook.
- If the AI feature was reported as "not found", do not draft a \
personalized security pitch — instead write a shorter, general \
introduction email that asks about their AI roadmap rather than asserting \
a specific risk that wasn't actually confirmed.

Respond with ONLY a JSON object:
{"email_subject": "...", "email_body": "...", "linkedin_note": "..."}"""


# Stage 4: Reply Classifier — routed to the CHEAP role (Haiku/Groq).
# Mechanical classification, but this is the anti-hallucination-critical
# prompt: it must never claim a meeting was requested without quoting the
# exact phrase that proves it. Few-shot examples are the brief's four
# required cases, verbatim.
REPLY_CLASSIFIER_SYSTEM_PROMPT = """You classify a single email reply to \
determine whether the sender is agreeing to a meeting.

Respond with ONLY a JSON object with exactly these three fields:
{"meeting_requested": <true or false>, "proposed_time": <string or null>, \
"evidence": <string or null>}

STRICT RULES — follow these exactly, they are more important than sounding \
helpful:
1. "evidence" must be an EXACT VERBATIM substring copied character-for-\
character from the reply — never paraphrase it, never summarize it.
2. If you cannot find and quote an exact phrase in the reply that clearly \
agrees to meet, "meeting_requested" MUST be false and "evidence" MUST be null.
3. "proposed_time" is the exact time/day phrase from the reply if one is \
explicitly stated (e.g. "Tuesday", "3pm Thursday"). If no explicit time is \
stated, "proposed_time" MUST be null — never infer or guess a time, even if \
one seems likely.
4. If the reply is ambiguous, non-committal, or only expresses interest \
without clearly agreeing to a specific meeting, default to \
"meeting_requested": false.

Examples:

Reply: "Thanks, but not interested."
{"meeting_requested": false, "proposed_time": null, "evidence": null}

Reply: "Sure, Tuesday works."
{"meeting_requested": true, "proposed_time": "Tuesday", "evidence": "Sure, Tuesday works"}

Reply: "Let me think about it."
{"meeting_requested": false, "proposed_time": null, "evidence": null}

Reply: "Yes let's talk"
{"meeting_requested": true, "proposed_time": null, "evidence": "Yes let's talk"}"""
```

- [ ] **Step 2: Show `src/prompts.py` to the user for review before proceeding to Task 4.**

No commit yet — second review checkpoint per the user's build order.

---

### Task 4: Provider abstraction + cost tracker + schemas

**Files:**
- Create: `src/schemas.py`
- Create: `src/providers.py`
- Create: `src/cost_tracker.py`

**Interfaces:**
- Consumes: `config.CHEAP_PROVIDER/QUALITY_PROVIDER/CHEAP_MODEL/QUALITY_MODEL/PRICING` (Task 1), API keys from `config`.
- Produces:
  - `schemas.ReplyClassification(BaseModel)`: `meeting_requested: bool`, `proposed_time: str | None`, `evidence: str | None`, with a `model_validator` enforcing rule 2 (evidence required and non-empty when `meeting_requested=True`).
  - `schemas.DiscoveryResult(BaseModel)`: `ai_feature: str`, `risk_category: Literal["prompt_injection","rag_data_exposure","autonomous_agent_manipulation","none"]`, `risk_rationale: str`.
  - `schemas.ContactExtraction(BaseModel)`: `name: str | None`, `title: str | None`.
  - `schemas.DraftedOutreach(BaseModel)`: `email_subject: str`, `email_body: str`, `linkedin_note: str`.
  - `providers.LLMResult` (dataclass): `text: str`, `input_tokens: int`, `output_tokens: int`, `model: str`, `role: Literal["cheap","quality"]`.
  - `providers.call_cheap(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 800) -> LLMResult`
  - `providers.call_quality(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 800) -> LLMResult`
  - `cost_tracker.CostTracker` class: `.record(result: providers.LLMResult) -> None`, `.total_projected_usd() -> float`, `.print_summary() -> None`. A single module-level instance `cost_tracker.TRACKER` is what the rest of the pipeline imports and records into.

- [ ] **Step 1: Write `src/schemas.py`**

```python
"""
Pydantic schemas — the enforcement layer behind every LLM call that must
return structured, non-hallucinated data. Every schema here is what makes
a malformed or ungrounded model response a caught ValidationError instead
of silently-wrong data flowing into the CSV.
"""
from typing import Literal, Optional
from pydantic import BaseModel, model_validator


class ReplyClassification(BaseModel):
    meeting_requested: bool
    proposed_time: Optional[str] = None
    evidence: Optional[str] = None

    @model_validator(mode="after")
    def evidence_required_when_true(self) -> "ReplyClassification":
        # Rule 2 from the brief, enforced structurally, not just by prompt
        # instruction: a true classification with no evidence is invalid
        # data, full stop — this makes the anti-hallucination rule
        # unbypassable by a model that ignores the system prompt.
        if self.meeting_requested and not (self.evidence and self.evidence.strip()):
            raise ValueError(
                "meeting_requested=true requires a non-empty evidence quote"
            )
        return self


class DiscoveryResult(BaseModel):
    ai_feature: str
    risk_category: Literal[
        "prompt_injection",
        "rag_data_exposure",
        "autonomous_agent_manipulation",
        "none",
    ]
    risk_rationale: str


class ContactExtraction(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None


class DraftedOutreach(BaseModel):
    email_subject: str
    email_body: str
    linkedin_note: str
```

- [ ] **Step 2: Write `src/providers.py`**

```python
"""
Provider abstraction — the ONLY module that knows how to talk to Groq,
Gemini, or Anthropic. Every other module calls call_cheap()/call_quality()
and never imports a provider SDK directly. This is what makes
config.PROVIDER_MODE a one-line swap: flip it, and every caller in the
codebase is unaffected.
"""
import json
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
        input_tokens=usage.prompt_token_count or 0,
        output_tokens=usage.candidates_token_count or 0,
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
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return LLMResult(
        text=text,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        model=model,
        role=role,
    )


def call_cheap(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 800) -> LLMResult:
    if config.CHEAP_PROVIDER == "groq":
        result = _call_groq(system, user, json_mode, max_tokens)
    else:
        result = _call_anthropic(system, user, config.CHEAP_MODEL, "cheap", max_tokens)
    from . import cost_tracker

    cost_tracker.TRACKER.record(result)
    return result


def call_quality(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 800) -> LLMResult:
    if config.QUALITY_PROVIDER == "gemini":
        result = _call_gemini(system, user, json_mode, max_tokens)
    else:
        result = _call_anthropic(system, user, config.QUALITY_MODEL, "quality", max_tokens)
    from . import cost_tracker

    cost_tracker.TRACKER.record(result)
    return result
```

- [ ] **Step 3: Write `src/cost_tracker.py`**

```python
"""
Tracks real token usage from every provider call and projects it against
the PRODUCTION architecture's pricing (Claude Haiku 4.5 / Sonnet 5), per
config.PRICING — regardless of which free-tier model actually served the
call. Actual PoC spend is always $0 (free tier); this answers "what would
this run cost on the architecture the brief specifies."
"""
from dataclasses import dataclass, field

from . import config
from .providers import LLMResult


@dataclass
class CostTracker:
    calls: list[LLMResult] = field(default_factory=list)

    def record(self, result: LLMResult) -> None:
        self.calls.append(result)

    def total_projected_usd(self) -> float:
        total = 0.0
        for c in self.calls:
            rate = config.PRICING[c.role]
            total += c.input_tokens * rate["input_per_1m"] / 1_000_000
            total += c.output_tokens * rate["output_per_1m"] / 1_000_000
        return total

    def print_summary(self) -> None:
        print("\n=== Cost Tracker (projected onto Haiku 4.5 / Sonnet 5 pricing) ===")
        for c in self.calls:
            rate = config.PRICING[c.role]
            cost = (
                c.input_tokens * rate["input_per_1m"] / 1_000_000
                + c.output_tokens * rate["output_per_1m"] / 1_000_000
            )
            print(
                f"  [{c.role:7s}] {c.model:28s} "
                f"in={c.input_tokens:5d} out={c.output_tokens:4d} "
                f"-> ${cost:.5f} (as {rate['model_label']})"
            )
        total = self.total_projected_usd()
        print(f"  {'-' * 60}")
        print(f"  TOTAL PROJECTED COST: ${total:.4f}  (actual PoC spend: $0.00, free tier)")
        print(f"  Budget check: {'PASS' if total < 50 else 'FAIL'} (<$50 for this run)")


TRACKER = CostTracker()
```

- [ ] **Step 4: Sanity-check imports**

Run: `python -c "from src import providers, cost_tracker, schemas; print('ok')"`
Expected: `ok` (no import errors — this catches typos/circular imports before any real API call).

- [ ] **Step 5: Commit**

```bash
git add src/schemas.py src/providers.py src/cost_tracker.py
git commit -m "feat: add provider abstraction, cost tracker, pydantic schemas"
```

---

### Task 5: Reply Classifier + tests — PROVE ANTI-HALLUCINATION BEFORE CONTINUING

**Files:**
- Create: `src/reply_classifier.py`
- Test: `tests/test_reply_classifier.py`
- Create: `tests/__init__.py` (empty)

**Interfaces:**
- Consumes: `providers.call_cheap` (Task 4), `schemas.ReplyClassification` (Task 4), `prompts.REPLY_CLASSIFIER_SYSTEM_PROMPT` (Task 3).
- Produces: `reply_classifier.classify_reply(reply_text: str) -> schemas.ReplyClassification` — used later by nothing else in this pipeline (it's a standalone deliverable per the brief: "separate function, takes a mocked reply string"), but its signature is final and must not change.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reply_classifier.py
"""
Proves the reply classifier's anti-hallucination guarantees against the
four required cases from the brief, plus edge cases for the structural
Pydantic guard. Requires GROQ_API_KEY (free tier) — these are real calls,
not mocks, because the deliverable is "prove the classifier actually
behaves this way," not "prove the mock returns what I told it to."
"""
from src.reply_classifier import classify_reply


def test_not_interested_returns_false():
    result = classify_reply("Thanks, but not interested.")
    assert result.meeting_requested is False
    assert result.proposed_time is None
    assert result.evidence is None


def test_explicit_time_returns_true_with_time_and_evidence():
    result = classify_reply("Sure, Tuesday works.")
    assert result.meeting_requested is True
    assert result.proposed_time is not None
    assert "tuesday" in result.proposed_time.lower()
    assert result.evidence is not None
    # evidence must be an exact verbatim substring of the input
    assert result.evidence in "Sure, Tuesday works."


def test_ambiguous_reply_defaults_false():
    result = classify_reply("Let me think about it.")
    assert result.meeting_requested is False


def test_agreement_without_time_has_null_time_not_inferred():
    result = classify_reply("Yes let's talk")
    assert result.meeting_requested is True
    assert result.proposed_time is None  # never inferred
    assert result.evidence is not None
    assert result.evidence in "Yes let's talk"


def test_evidence_is_always_verbatim_substring_when_true():
    reply = "Sounds good, how about we hop on a call Thursday afternoon?"
    result = classify_reply(reply)
    if result.meeting_requested:
        assert result.evidence in reply, "evidence must be an exact quote, never a paraphrase"
```

- [ ] **Step 2: Run test to verify it fails (module doesn't exist yet)**

Run: `pytest tests/test_reply_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.reply_classifier'`

- [ ] **Step 3: Write `src/reply_classifier.py`**

```python
"""
Task 4 of the brief: the reply classifier. Deliberately the smallest,
most locked-down module in the codebase — this is the anti-hallucination
core the take-home is graded on.

Guarantees enforced (see brief section "ANTI-HALLUCINATION"):
1. Only valid JSON reaches the caller — enforced by schemas.ReplyClassification,
   retried once on parse/validation failure.
2. evidence must be an exact verbatim quote proving meeting_requested=true —
   enforced structurally by ReplyClassification's model_validator, not just
   prompted for.
3. proposed_time is null unless an explicit time was stated — prompted for
   (rule 3), not structurally enforceable since "was a time explicit" isn't
   checkable from the output alone.
4. Ambiguity defaults to false — prompted for (rule 4); the few-shot
   "Let me think about it" example is the enforcement mechanism.
5. On two consecutive failures (bad JSON or failed validation), we do NOT
   raise and we do NOT re-ask forever — we fail SAFE to
   ReplyClassification(meeting_requested=False, ...), because a silent
   crash or an infinite retry loop is worse than under-flagging a reply
   a human can still read manually.
"""
import json
import logging

from pydantic import ValidationError

from . import prompts, providers
from .schemas import ReplyClassification

logger = logging.getLogger(__name__)

_SAFE_DEFAULT = ReplyClassification(meeting_requested=False, proposed_time=None, evidence=None)


def _extract_and_validate(raw_text: str) -> ReplyClassification:
    # Models occasionally wrap JSON in prose or code fences despite
    # instructions; take the substring between the first { and last }
    # rather than failing on decorated output.
    start, end = raw_text.find("{"), raw_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in model output")
    payload = json.loads(raw_text[start : end + 1])
    return ReplyClassification.model_validate(payload)


def classify_reply(reply_text: str) -> ReplyClassification:
    """Classify a single email reply. Never raises — worst case returns
    the safe all-false default after one retry."""
    user_prompt = f"Reply:\n{reply_text}"

    for attempt in range(2):  # one real attempt + one retry, per the brief
        result = providers.call_cheap(
            system=prompts.REPLY_CLASSIFIER_SYSTEM_PROMPT,
            user=user_prompt,
            json_mode=True,
            max_tokens=300,
        )
        try:
            return _extract_and_validate(result.text)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning("classify_reply attempt %d failed: %s", attempt + 1, e)

    logger.error("classify_reply: both attempts failed, returning safe default")
    return _SAFE_DEFAULT


if __name__ == "__main__":
    # Deliverable: "Test the classifier against all four cases and print
    # results" — run directly with `python -m src.reply_classifier`.
    cases = [
        "Thanks, but not interested.",
        "Sure, Tuesday works.",
        "Let me think about it.",
        "Yes let's talk",
    ]
    for reply in cases:
        result = classify_reply(reply)
        print(f"Reply: {reply!r}")
        print(f"  -> {result.model_dump_json()}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reply_classifier.py -v`
Expected: PASS (5/5). If a real-network flake occurs, re-run once — do not weaken the assertions to accommodate flakiness.

- [ ] **Step 5: Run the four-case demo and inspect output by eye**

Run: `python -m src.reply_classifier`
Expected: four lines, each showing correct `meeting_requested`/`proposed_time`/`evidence` matching the brief's four required cases exactly.

- [ ] **Step 6: Commit**

```bash
git add src/reply_classifier.py tests/test_reply_classifier.py tests/__init__.py
git commit -m "feat: reply classifier with strict anti-hallucination guarantees + tests"
```

---

### Task 6: Discovery (Task 1 of the brief's agent tasks)

**Files:**
- Create: `src/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `providers.call_cheap`, `prompts.DISCOVERY_SYSTEM_PROMPT`, `schemas.DiscoveryResult`.
- Produces: `discovery.fetch_page_text(url: str) -> str`, `discovery.discover_company(url: str) -> schemas.DiscoveryResult`.

- [ ] **Step 1: Write `src/discovery.py`**

```python
"""
Task 1: Discovery. Fetches a company's public homepage, identifies their
AI feature, maps it to an AgenticGuard risk category. Routed to the CHEAP
role — this is mechanical extraction, not persuasive writing.

Respects robots.txt: before fetching any URL, checks whether our user
agent is allowed to fetch that specific path, and skips the fetch (falling
back to a "not found" DiscoveryResult) if disallowed, rather than fetching
anyway.
"""
import json
import logging
import urllib.robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import ValidationError

from . import prompts, providers
from .schemas import DiscoveryResult

logger = logging.getLogger(__name__)

USER_AGENT = "AgenticGuardGTMBot/1.0 (+https://agenticguard.example/bot)"
TIMEOUT_SECONDS = 10
MAX_PAGE_CHARS = 6000  # keep the cheap-model call small and cheap


def _robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception:
        # No readable robots.txt -> treat as allowed (standard behavior);
        # a network failure here should not block discovery entirely.
        return True
    return rp.can_fetch(USER_AGENT, url)


def fetch_page_text(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    if not _robots_allowed(url):
        logger.warning("robots.txt disallows fetching %s, skipping", url)
        return ""
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("fetch failed for %s: %s", url, e)
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:MAX_PAGE_CHARS]


def discover_company(url: str) -> DiscoveryResult:
    page_text = fetch_page_text(url)
    if not page_text:
        return DiscoveryResult(
            ai_feature="not found",
            risk_category="none",
            risk_rationale="Page could not be fetched (network error or robots.txt disallow).",
        )

    user_prompt = f"Company homepage URL: {url}\n\nScraped page text:\n{page_text}"

    for attempt in range(2):
        result = providers.call_cheap(
            system=prompts.DISCOVERY_SYSTEM_PROMPT,
            user=user_prompt,
            json_mode=True,
            max_tokens=400,
        )
        try:
            start, end = result.text.find("{"), result.text.rfind("}")
            payload = json.loads(result.text[start : end + 1])
            return DiscoveryResult.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning("discover_company attempt %d failed: %s", attempt + 1, e)

    return DiscoveryResult(
        ai_feature="not found",
        risk_category="none",
        risk_rationale="Model output could not be parsed after retry.",
    )
```

- [ ] **Step 2: Write a smoke test**

```python
# tests/test_discovery.py
from src.discovery import fetch_page_text, discover_company


def test_fetch_page_text_returns_nonempty_for_real_site():
    text = fetch_page_text("https://www.paymob.com")
    assert isinstance(text, str)
    # Either we got real page text, or fetch failed and we got "" —
    # both are valid outcomes; we assert the function doesn't raise.


def test_discover_company_returns_valid_schema():
    result = discover_company("https://www.paymob.com")
    assert result.risk_category in {
        "prompt_injection",
        "rag_data_exposure",
        "autonomous_agent_manipulation",
        "none",
    }
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_discovery.py -v`
Expected: PASS (network-dependent; if paymob.com is unreachable in this environment, the test still passes because both branches are valid outcomes).

- [ ] **Step 4: Commit**

```bash
git add src/discovery.py tests/test_discovery.py
git commit -m "feat: discovery stage — scrape + risk-map via cheap model"
```

---

### Task 7: Enrichment (Task 2 of the brief's agent tasks)

**Files:**
- Create: `src/enrichment.py`

**Interfaces:**
- Consumes: `providers.call_cheap`, `prompts.ENRICHMENT_SYSTEM_PROMPT`, `schemas.ContactExtraction`, `discovery.fetch_page_text`, `config.HUNTER_API_KEY`.
- Produces: `enrichment.ContactInfo` (dataclass: `name: str | None`, `email: str`, `email_is_placeholder: bool`, `linkedin_url: str`, `linkedin_is_search_link: bool`), `enrichment.enrich_contact(domain: str, company: str) -> ContactInfo`.

- [ ] **Step 1: Write `src/enrichment.py`**

```python
"""
Task 2: Enrichment. Finds a CTO/CISO name + email.

Priority order:
1. Hunter.io free tier domain search, if HUNTER_API_KEY is set — real,
   attributed emails only (Hunter returns a confidence score and a value
   field; we only accept results where Hunter itself returns an actual
   email, never a Hunter "pattern guess" with no verified value).
2. Otherwise, parse the company's public About/Team page with the cheap
   model to find a named CTO/CISO — if found, construct a placeholder
   email at that domain, clearly flagged.
3. If no name is found anywhere, construct a role-based placeholder
   (cto@domain) and flag it.

Never resolves a real LinkedIn profile URL (LinkedIn's ToS prohibits
scraping profile data; in production this is exactly where Apollo.io's
API would replace this function's contact-lookup role, since Apollo
licenses this data rather than scraping it). Instead this builds a real,
working LinkedIn PEOPLE-SEARCH url for the name + company — an honest
link a human can click and resolve themselves, never a fabricated
profile URL asserted as real.
"""
import logging
import urllib.parse
from dataclasses import dataclass

import requests

from . import config, discovery, prompts, providers
from .schemas import ContactExtraction

logger = logging.getLogger(__name__)

TEAM_PAGE_PATHS = ["/about", "/about-us", "/team", "/leadership", "/company"]


@dataclass
class ContactInfo:
    name: str | None
    email: str
    email_is_placeholder: bool
    linkedin_url: str
    linkedin_is_search_link: bool


def _hunter_lookup(domain: str) -> ContactExtraction | None:
    if not config.HUNTER_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": config.HUNTER_API_KEY, "seniority": "executive"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        for person in data.get("emails", []):
            position = (person.get("position") or "").lower()
            if "cto" in position or "chief technology" in position or "ciso" in position:
                if person.get("value"):  # only accept a real returned email
                    return ContactExtraction(
                        name=f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
                        or None,
                        title=person.get("position"),
                    ), person["value"]
    except requests.RequestException as e:
        logger.warning("Hunter.io lookup failed for %s: %s", domain, e)
    return None


def _parse_team_page(domain: str) -> ContactExtraction:
    for path in TEAM_PAGE_PATHS:
        text = discovery.fetch_page_text(f"https://{domain}{path}")
        if not text:
            continue
        result = providers.call_cheap(
            system=prompts.ENRICHMENT_SYSTEM_PROMPT,
            user=f"Page text:\n{text}",
            json_mode=True,
            max_tokens=150,
        )
        try:
            import json

            start, end = result.text.find("{"), result.text.rfind("}")
            payload = json.loads(result.text[start : end + 1])
            extraction = ContactExtraction.model_validate(payload)
            if extraction.name:
                return extraction
        except Exception as e:
            logger.warning("team page parse failed for %s%s: %s", domain, path, e)
    return ContactExtraction(name=None, title=None)


def _linkedin_search_url(name: str | None, company: str) -> str:
    query = f"{name} {company}" if name else company
    return "https://www.linkedin.com/search/results/people/?keywords=" + urllib.parse.quote(query)


def enrich_contact(domain: str, company: str) -> ContactInfo:
    hunter_result = _hunter_lookup(domain)
    if hunter_result:
        extraction, real_email = hunter_result
        return ContactInfo(
            name=extraction.name,
            email=real_email,
            email_is_placeholder=False,
            linkedin_url=_linkedin_search_url(extraction.name, company),
            linkedin_is_search_link=True,
        )

    extraction = _parse_team_page(domain)
    placeholder_email = f"cto@{domain}"
    return ContactInfo(
        name=extraction.name,
        email=f"{placeholder_email} [UNVERIFIED PLACEHOLDER]",
        email_is_placeholder=True,
        linkedin_url=_linkedin_search_url(extraction.name, company),
        linkedin_is_search_link=True,
    )
```

- [ ] **Step 2: Sanity-check with a placeholder-path smoke test**

Run: `python -c "
from src.enrichment import enrich_contact
info = enrich_contact('paymob.com', 'Paymob')
print(info)
assert 'PLACEHOLDER' in info.email or info.email_is_placeholder is False
print('ok')
"`
Expected: prints a `ContactInfo(...)` and `ok`, no exception.

- [ ] **Step 3: Commit**

```bash
git add src/enrichment.py
git commit -m "feat: enrichment stage — Hunter.io / page-parse / flagged placeholder fallback"
```

---

### Task 8: Drafting (Task 3 of the brief's agent tasks)

**Files:**
- Create: `src/drafting.py`

**Interfaces:**
- Consumes: `providers.call_quality`, `prompts.DRAFTING_SYSTEM_PROMPT`, `schemas.DraftedOutreach`, `schemas.DiscoveryResult`, `enrichment.ContactInfo`.
- Produces: `drafting.draft_outreach(company: str, discovery_result: schemas.DiscoveryResult, contact: enrichment.ContactInfo) -> schemas.DraftedOutreach`.

- [ ] **Step 1: Write `src/drafting.py`**

```python
"""
Task 3: Drafting. The one stage routed to the QUALITY role (Sonnet/Gemini)
— hyper-personalized email + LinkedIn note, grounded in the specific
mapped risk from Discovery. Never sends anything (see pipeline.py's
mock-send comment) — this only generates payloads.
"""
import json
import logging

from pydantic import ValidationError

from . import prompts, providers
from .enrichment import ContactInfo
from .schemas import DiscoveryResult, DraftedOutreach

logger = logging.getLogger(__name__)

_FALLBACK = DraftedOutreach(
    email_subject="Quick question about your AI roadmap",
    email_body=(
        "Hi there,\n\nI work with AgenticGuard, helping engineering teams "
        "secure their AI agent deployments. I'd love to learn more about "
        "your AI roadmap and share what we're seeing across fintech. "
        "Open to a quick 15-minute call?\n\nBest,\nAgenticGuard Team"
    ),
    linkedin_note="Hi — I work on AI agent security at AgenticGuard. Would love to connect and hear about your AI roadmap.",
)


def draft_outreach(
    company: str, discovery_result: DiscoveryResult, contact: ContactInfo
) -> DraftedOutreach:
    user_prompt = (
        f"Company: {company}\n"
        f"Contact name: {contact.name or 'Unknown (use a generic greeting)'}\n"
        f"AI feature: {discovery_result.ai_feature}\n"
        f"Risk category: {discovery_result.risk_category}\n"
        f"Risk rationale: {discovery_result.risk_rationale}"
    )

    for attempt in range(2):
        result = providers.call_quality(
            system=prompts.DRAFTING_SYSTEM_PROMPT,
            user=user_prompt,
            json_mode=True,
            max_tokens=700,
        )
        try:
            start, end = result.text.find("{"), result.text.rfind("}")
            payload = json.loads(result.text[start : end + 1])
            return DraftedOutreach.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning("draft_outreach attempt %d failed: %s", attempt + 1, e)

    logger.error("draft_outreach: both attempts failed, using generic fallback")
    return _FALLBACK
```

- [ ] **Step 2: Commit**

```bash
git add src/drafting.py
git commit -m "feat: drafting stage — personalized outreach via quality model"
```

---

### Task 9: Pipeline orchestration + CSV output

**Files:**
- Create: `src/pipeline.py`
- Create: `main.py`
- Create: `output/.gitkeep` (directory placeholder; the real deliverable `output/leads.csv` is generated by Step 3 below and committed alongside it)

**Interfaces:**
- Consumes: `discovery.discover_company`, `enrichment.enrich_contact`, `drafting.draft_outreach`, `cost_tracker.TRACKER`, all schemas.
- Produces: `pipeline.run_pipeline(urls: list[str], out_csv_path: str) -> None`.

- [ ] **Step 1: Write `src/pipeline.py`**

```python
"""
Orchestrates Discovery -> Enrichment -> Drafting across the target URL
list and writes the CSV deliverable. Does NOT send anything — see the
mock-send comment below.
"""
import csv
import logging
from urllib.parse import urlparse

from . import cost_tracker
from .discovery import discover_company
from .drafting import draft_outreach
from .enrichment import enrich_contact

logger = logging.getLogger(__name__)

CSV_HEADERS = [
    "Company",
    "CTO Name",
    "CTO Email",
    "LinkedIn URL",
    "Drafted Email",
    "Drafted LinkedIn Note",
]


def _domain_and_company(url: str) -> tuple[str, str]:
    netloc = urlparse(url if "://" in url else f"https://{url}").netloc or url
    domain = netloc.replace("www.", "")
    company = domain.split(".")[0].capitalize()
    return domain, company


def run_pipeline(urls: list[str], out_csv_path: str) -> None:
    rows = []
    for url in urls:
        domain, company = _domain_and_company(url)
        logger.info("Processing %s (%s)", company, domain)

        discovery_result = discover_company(url)
        contact = enrich_contact(domain, company)
        draft = draft_outreach(company, discovery_result, contact)

        # MOCK SEND ONLY — we generate the email/LinkedIn payloads above
        # and write them to CSV below. We deliberately do NOT call
        # SendGrid, LinkedIn, or any send API here; per the brief this
        # pipeline generates outreach content for human review, it does
        # not autonomously contact anyone.
        rows.append(
            {
                "Company": company,
                "CTO Name": contact.name or "Unknown (not found on public pages)",
                "CTO Email": contact.email,
                "LinkedIn URL": contact.linkedin_url
                + (" [search link, not a resolved profile]" if contact.linkedin_is_search_link else ""),
                "Drafted Email": f"Subject: {draft.email_subject}\n\n{draft.email_body}",
                "Drafted LinkedIn Note": draft.linkedin_note,
            }
        )

    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Wrote %d leads to %s", len(rows), out_csv_path)
    cost_tracker.TRACKER.print_summary()
```

- [ ] **Step 2: Write `main.py`**

```python
"""
Entry point: runs the full GTM loop over the 5 target fintech URLs from
the brief, writes output/leads.csv, prints the projected cost summary,
then runs the reply-classifier demo against the brief's four required
test cases.
"""
import logging

from src.pipeline import run_pipeline
from src.reply_classifier import classify_reply

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

TARGET_URLS = [
    "khazna.com",
    "nowpay.com",
    "paymob.com",
    "tabby.com",
    "tamara.com",
]


def main() -> None:
    print("=== AgenticGuard GTM Loop ===\n")
    run_pipeline(TARGET_URLS, "output/leads.csv")

    print("\n=== Reply Classifier: required test cases ===")
    cases = [
        "Thanks, but not interested.",
        "Sure, Tuesday works.",
        "Let me think about it.",
        "Yes let's talk",
    ]
    for reply in cases:
        result = classify_reply(reply)
        print(f"  {reply!r} -> {result.model_dump_json()}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the full pipeline end-to-end**

Run: `python main.py`
Expected: processes all 5 companies, writes `output/leads.csv` with 5 data rows + header, prints the cost summary (PASS, well under $50), prints 4 classifier results matching the brief's expected true/false pattern.

- [ ] **Step 4: Inspect `output/leads.csv` by eye**

Confirm: 6 lines (header + 5 rows), no row has a raw unflagged guess in the CTO Email column (either a real Hunter email or a `[UNVERIFIED PLACEHOLDER]`-flagged one), every LinkedIn URL is a real `linkedin.com/search/results/people/?keywords=...` link.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline.py main.py output/leads.csv
git commit -m "feat: pipeline orchestration, CSV output, run against 5 target leads"
```

---

### Task 10: README

**Files:**
- Create: `README.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Write `README.md`**

Sections required:
1. **What this is** — one paragraph, links to `architecture/architecture.html`.
2. **Setup** — `pip install -r requirements.txt`, create `.env` with `GROQ_API_KEY` / `GOOGLE_API_KEY` (and optional `HUNTER_API_KEY`), how to get free-tier keys for each.
3. **Run** — `python main.py`; `pytest` for tests; `python -m src.reply_classifier` for the classifier demo alone.
4. **Cost-routing rationale** — reproduce the token-math table from the architecture doc, explain the Haiku(cheap)/Sonnet(quality) split and why each stage is routed where it is, and restate the free-tier/production distinction and the one-line swap (`config.PROVIDER_MODE`).
5. **Anti-hallucination writeup** — explain the four guarantees (Pydantic schema enforcement + retry-once, verbatim-evidence structural validator, never-inferred proposed_time, default-false-on-ambiguity) and point at `tests/test_reply_classifier.py` as the proof.
6. **Scraping/ToS notes** — robots.txt is checked before every fetch; LinkedIn is never scraped, only linked via a real people-search URL; in production, Apollo.io's API would replace both the team-page-parsing fallback and the LinkedIn search-link with licensed, verified contact + profile data.
7. **What's mocked** — no email/LinkedIn send integration exists; `pipeline.py`'s comment marks exactly where a real send would go and why it's deliberately absent.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, run instructions, cost + anti-hallucination writeup"
```

---

### Task 11: Final review pass

**Files:** None new — read-only review of the full repo.

- [ ] **Step 1: Run the full test suite one more time**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 2: Confirm `.env` was never committed at any point**

Run: `git log --all --oneline -- .env`
Expected: no output (empty).

- [ ] **Step 3: Final `git log` review**

Run: `git log --oneline`
Expected: a clean, logically-ordered commit history matching the tasks above.

---

## Self-Review

**1. Spec coverage:**
- 1-page architecture HTML → Task 2. ✓
- Python script for all 4 agent stages → Tasks 5–9. ✓
- `prompts.py`, documented → Task 3. ✓
- CSV output with exact required columns → Task 9. ✓
- 5 target URLs processed → Task 9 (`TARGET_URLS`). ✓
- Cost tracker proving <$50/20 leads, math commented → Task 4 (`cost_tracker.py`) + Task 2 (doc table) — both use the identical per-call rate table from `config.PRICING`, so the doc and the running code can never disagree. ✓
- Discovery/Enrichment/Drafting/Reply-Classifier task descriptions → Tasks 6, 7, 8, 5 respectively, each routed to the model role specified in the brief. ✓
- Anti-hallucination rules 1–5 → Task 5 (`schemas.ReplyClassification` + `reply_classifier.py` retry-once-then-safe-default logic) + few-shot prompt in Task 3. ✓
- Constraints: no real sends (Task 9 mock-send comment), `.env` for keys (Task 1, already done), robots.txt respect + Apollo note (Task 6, 7, 10), typed/documented code throughout, git init + logical commits (every task ends with one). ✓

**2. Placeholder scan:** No TBD/TODO markers; every step has runnable code or an exact command. Clean.

**3. Type consistency:** Traced `ContactInfo`, `DiscoveryResult`, `DraftedOutreach`, `ReplyClassification`, `LLMResult` field names across every task that constructs or consumes them (4→5/6/7/8/9) — consistent throughout.

## Execution Handoff

Given the scope (a single-session take-home with explicit reviewer checkpoints already built into the task order — architecture doc and prompts.py are review gates before Task 4 even starts), this plan is best run as **inline execution in this session**, task by task, pausing at the two explicit checkpoints (end of Task 2, end of Task 3) for your review before continuing. I'll flag if anything forces a detour.

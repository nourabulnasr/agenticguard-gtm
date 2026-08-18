# AgenticGuard — Autonomous GTM Loop

A 4-stage GTM automation pipeline for AgenticGuard (AI agent security):
**Discovery → Enrichment → Drafting → Reply Classification**, run against
5 fintech targets (khazna.com, nowpay.com, paymob.com, tabby.com, tamara.com).

Architecture map (1-page, print-to-PDF): [`architecture/architecture.html`](architecture/architecture.html)

## What this is

Given a list of company URLs, the pipeline:
1. **Discovers** the AI feature each company publicly markets and maps it to an AgenticGuard risk category (prompt injection / RAG data exposure / autonomous agent manipulation).
2. **Enriches** the lead with a CTO/CISO contact — a real email via Hunter.io if configured, otherwise parsed from public team pages, otherwise a placeholder that is **clearly flagged as unverified in the data itself**.
3. **Drafts** a hyper-personalized cold email + LinkedIn note grounded in the specific feature/risk found (never sent — see "What's mocked" below).
4. Separately, a **reply classifier** takes a mocked inbound reply and returns strict, schema-enforced JSON on whether a meeting was requested — this is the anti-hallucination centerpiece of the take-home.

Output: [`output/leads.csv`](output/leads.csv) with columns `Company, CTO Name, CTO Email, LinkedIn URL, Drafted Email, Drafted LinkedIn Note`.

## Setup

```bash
python -m venv .venv
. .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\Activate.ps1 for PowerShell
pip install -r requirements.txt
```

Create `.env` in the project root:

```
GROQ_API_KEY=your_groq_key       # free tier: console.groq.com
GOOGLE_API_KEY=your_google_key   # free tier: aistudio.google.com/apikey
HUNTER_API_KEY=                  # optional, free tier: hunter.io — leave blank to use the page-parse/placeholder fallback
ANTHROPIC_API_KEY=               # only needed if you flip config.PROVIDER_MODE to "anthropic"
```

Both `GROQ_API_KEY` and `GOOGLE_API_KEY` are required for the PoC as configured. Never commit `.env` (already gitignored).

## Run

```bash
python main.py                        # full pipeline: 5 leads -> output/leads.csv, cost summary, classifier demo
python -m src.reply_classifier         # classifier alone, against the brief's 4 required cases
pytest -v                              # full test suite (real API calls, not mocked)
```

## Cost-routing rationale

**The architecture targets Claude Haiku 4.5 (cheap role) and Claude Sonnet 5 (quality role)** — that's what's costed and what ships in production. The **running PoC swaps in free-tier providers** so it costs $0 to demonstrate the logic without a card:

| Role | Production model | PoC model (free tier) | Used for |
|---|---|---|---|
| Cheap | `claude-haiku-4-5-20251001` | Groq `openai/gpt-oss-20b`* | Discovery risk-mapping, Enrichment page-parsing, Reply classification |
| Quality | `claude-sonnet-5` | Gemini `gemini-3.1-flash-lite`* | Drafting only |

\* **Not** the exact models named in the original brief (`llama-3.3-70b-versatile` / a `gemini-2.5-*` model) — both were verified live against real API keys during this build and found unavailable (see "Model availability caveat" below). Swapped to confirmed-working equivalents that fill the same routing role.

The two-tier routing intent is identical regardless of provider: mechanical, high-volume work (scraping, classification) goes to the cheap role; only the one task that needs persuasive voice — Drafting — pays quality-tier rates. Provider selection is **one config line**:

```python
# src/config.py
PROVIDER_MODE: Literal["free_tier", "anthropic"] = "free_tier"
```

Flip it to `"anthropic"` and every call in the codebase routes directly to Claude — no other code changes, because every module calls `providers.call_cheap()` / `providers.call_quality()` and never imports a provider SDK directly.

**Token math, proving <$50 for 20 leads** (standard Anthropic pricing, not the Sonnet 5 intro rate that expires 2026-08-31 — the margin holds either way):

| Stage | Model | Est. in/out tokens | Cost/lead |
|---|---|---|---|
| Discovery | Haiku 4.5 | 3,000 / 300 | $0.0045 |
| Enrichment | Haiku 4.5 | 2,000 / 150 | $0.0028 |
| Drafting | Sonnet 5 | 1,500 / 500 | $0.0120 |
| Reply classify (incl. 1 retry) | Haiku 4.5 | 1,000 / 200 | $0.0020 |
| **Total** | | | **$0.0213/lead → $0.43/20 leads** |

**~117× under the $50 budget.** Full math and the same table live in `architecture/architecture.html`; `src/cost_tracker.py` computes the identical math from real per-call token counts at runtime (see "What the cost tracker actually measures" below) — the doc and the code can't drift apart because both read `config.PRICING`.

Running `python main.py` against the real 5 targets came in at **$0.0386 projected** — even lower than the conservative estimate above, because real prompts were shorter than the padded per-lead estimate.

### What the cost tracker actually measures

`cost_tracker.py` records real token usage from every PoC call (Groq/Gemini) but prices it at **Haiku 4.5 / Sonnet 5 rates**, not the free tier's real cost (which is always $0). It answers "what would this run cost in production," not "what did this run bill" — that's the number the brief's cost-routing criterion is actually asking for.

## Anti-hallucination writeup

The reply classifier (`src/reply_classifier.py`) is a 5-step guard chain, diagrammed in `architecture/architecture.html`:

1. **Pydantic schema gate** — only valid JSON matching `{meeting_requested, proposed_time, evidence}` reaches the caller (`schemas.ReplyClassification`).
2. **Structural evidence check** — this is the load-bearing guard. `meeting_requested=true` requires a non-empty `evidence` string, enforced by a `@model_validator` on the schema itself, *not just a prompt instruction*. A model that ignores the system prompt's rule 2 still can't produce invalid data — the `ValidationError` fires regardless of what the model says.
3. **`proposed_time` stays `null`** unless an explicit time is stated — prompted for (schema can't structurally verify "was this actually explicit"), reinforced by the few-shot example `"Yes let's talk"` → `proposed_time: null`.
4. **Retry once** on JSON parse or schema validation failure (`classify_reply`'s `for attempt in range(2)` loop) — matches the brief's "retry once" scope exactly; it does **not** retry on provider/network errors (rate limits, connection failures), which propagate instead of being silently swallowed, since an outage is an infrastructure problem, not a hallucination risk.
5. **Safe-false default** if both attempts fail to produce valid JSON — never crashes, never guesses.

**Known tradeoff** (documented on the architecture page): ambiguous soft-interest phrases like *"maybe later"* or *"I'll circle back"* resolve to `meeting_requested=false`. We under-capture rather than over-claim — a false positive here means a rep chases a meeting that was never actually offered, which is the worse failure mode.

**Proof**: `tests/test_reply_classifier.py` runs 6 cases — the brief's 4 required cases plus 2 edge cases (verbatim-evidence substring check, the "maybe later" tradeoff) — against **real Groq calls, not mocks**, because the deliverable is proving the classifier actually behaves this way, not proving a mock returns what it was told to. `python -m src.reply_classifier` prints the 4 required cases directly.

The same discipline extends past the classifier: Discovery's prompt explicitly instructs "say `not found` rather than invent a plausible AI feature," and was tightened mid-build after live testing surfaced a real gap — see "What real-world testing caught," below.

## Scraping / ToS notes

- Every fetch checks `robots.txt` via `urllib.robotparser` before requesting a page (`discovery.py::_robots_allowed`); disallowed paths are skipped, not fetched anyway.
- **LinkedIn is never scraped.** LinkedIn's ToS prohibits it. Instead, `enrichment.py` builds a real, working `linkedin.com/search/results/people/?keywords=...` URL — a genuine link a human can click and resolve themselves, not a fabricated profile URL asserted as real. It's flagged in the CSV as `[search link, not a resolved profile]`.
- **In production, this is exactly where Apollo.io's API would replace two things**: the team-page-parsing fallback in `enrichment.py` (Apollo licenses verified org-chart data rather than scraping About pages) and the LinkedIn search-link workaround (Apollo resolves actual profile URLs through a licensed data agreement, not scraping).

## What's mocked

**Nothing is ever sent.** `pipeline.py` generates the email and LinkedIn note payloads and writes them to CSV — there is no SendGrid, LinkedIn API, or any send integration wired up. The exact point where a real send would go is marked with a comment in `pipeline.py`:

```python
# MOCK SEND ONLY — we generate the email/LinkedIn payloads above
# and write them to CSV below. We deliberately do NOT call
# SendGrid, LinkedIn, or any send API here...
```

The reply classifier's input is also mocked — it takes a plain reply string (see the 4 test cases), not a live inbox integration.

## Model availability caveat (verify-don't-guess, applied to this build too)

The brief named `llama-3.3-70b-versatile` (Groq) as the intended cheap-role model. Verified live against a real Groq key during this build (`client.models.list()`): **retired from the catalog**, 404 `model_not_found`. Similarly, `gemini-2.5-flash` / `gemini-2.5-flash-lite` both 404 as "no longer available to new users" despite still appearing in `models.list()` — a live inconsistency in Google's API surface, not something guessable from docs. `gemini-3.6-flash` and `gemini-flash-latest` work but are thinking models that burned 800+ hidden reasoning tokens on a simple drafting prompt (risking silent mid-JSON truncation) and were hitting `503` high-demand errors during testing.

Final choices, both verified working end-to-end against all 5 real targets: **`openai/gpt-oss-20b`** (Groq, cheap role, `reasoning_effort="low"` to keep its trace out of the returned JSON) and **`gemini-3.1-flash-lite`** (Google AI Studio, quality role — no hidden thinking tax, predictable token usage). `providers.py` also adds a small infra-level retry for transient `503`/`429`/5xx errors, separate from the anti-hallucination retry-once-on-parse-failure logic.

If your keys have access to the originally-named models, swap them back in `src/config.py` — nothing else in the codebase depends on a specific model name.

## What real-world testing caught

Two prompt gaps only surfaced by actually running the pipeline against the 5 real targets, not from reasoning about the prompts in the abstract:

- **Discovery**: `khazna.com`'s homepage describes a real AI feature (camera-based card scanning) that doesn't cleanly match any of the 3 risk categories. The original prompt only permitted `risk_category: "none"` when no feature was found at all, forcing an implicit choice between an inaccurate category label or an unspecified behavior. Fixed: `"none"` is now explicitly valid for both "nothing found" and "found something that doesn't fit" — an honest `"none"` beats a forced bad-fit label.
- **Drafting**: `paymob.com`'s homepage describes real ML-based fraud detection that doesn't map to a risk category either. The drafting prompt's "don't force a security pitch" fallback only covered `ai_feature == "not found"`, not `risk_category == "none"` with a real feature present — the model handled the untested case gracefully, but by luck, not by instruction. Fixed the same way: the fallback rule now covers both cases explicitly.

Both fixes are committed with the specific real-URL evidence that surfaced them (see git log).

## Project structure

```
architecture/architecture.html   1-page architecture map (print-to-PDF)
src/
  config.py                      Provider routing + pricing (the swappable line)
  prompts.py                     All 4 system prompts, documented
  schemas.py                     Pydantic schemas — the structural anti-hallucination layer
  providers.py                   Groq / Gemini / Anthropic call abstraction + transient retry
  cost_tracker.py                Real token usage -> projected Haiku/Sonnet cost
  discovery.py                   Task 1: scrape + risk-map
  enrichment.py                  Task 2: CTO/CISO lookup, Hunter.io / parse / flagged placeholder
  drafting.py                    Task 3: personalized email + LinkedIn note
  reply_classifier.py            Task 4: strict-JSON meeting-intent classification
  pipeline.py                    Orchestration + CSV writer
main.py                          Entry point — runs the 5 target leads end-to-end
tests/                           pytest suite (real API calls, not mocked)
output/leads.csv                 Generated deliverable
```

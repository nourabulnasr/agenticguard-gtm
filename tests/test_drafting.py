"""
Drafting had zero test coverage before this file — a real gap flagged in
the red-team pass. These are necessarily softer checks than the reply
classifier's (drafting output is generative prose, not strict-schema
JSON), but they lock in the three-case behavior the drafting prompt
depends on: real feature + real risk -> name both; real feature + no
risk match -> reference the feature, no invented risk; no feature found
-> explicit honest disclosure, no fabricated familiarity.
"""
import re

from src.drafting import draft_outreach
from src.enrichment import ContactInfo
from src.schemas import DiscoveryResult

# Matches a claim tied specifically to the TARGET company (e.g. "your
# prompt injection risk", "you are exposed to prompt injection") without
# false-flagging AgenticGuard's own generic self-description ("we help
# teams secure against prompt injection..."), and without the classic
# substring trap where bare "rag" matches inside "leveraging"/"average".
_TARGETED_RISK_CLAIM = re.compile(
    r"\byour\b[^.]{0,60}\b(prompt injection|rag data exposure|autonomous agent)\b"
    r"|\b(prompt injection|rag data exposure|autonomous agent)\b[^.]{0,60}\byour\b",
    re.IGNORECASE,
)

_CONTACT = ContactInfo(
    name="Sara Ahmed",
    email="cto@example.com [UNVERIFIED PLACEHOLDER]",
    email_is_placeholder=True,
    linkedin_url="https://www.linkedin.com/search/results/people/?keywords=Sara+Ahmed",
    linkedin_is_search_link=True,
)


def test_case_a_names_both_feature_and_risk_mechanism():
    discovery_result = DiscoveryResult(
        ai_feature="AI-powered support chatbot that answers account and billing questions from free-text input",
        risk_category="prompt_injection",
        risk_rationale="The chatbot accepts free-text user input and acts on it directly.",
    )
    draft = draft_outreach("ExampleFintech", discovery_result, _CONTACT)
    body_lower = draft.email_body.lower()
    # The feature must be named specifically, not just "your AI systems".
    assert "chatbot" in body_lower
    # The risk mechanism must be named in plain language, not just the
    # internal snake_case category id.
    assert "prompt injection" in body_lower or "inject" in body_lower


def test_case_b_references_real_feature_without_inventing_a_risk():
    discovery_result = DiscoveryResult(
        ai_feature="Camera-based card identification from a photo",
        risk_category="none",
        risk_rationale="Image recognition doesn't match any of the three risk categories.",
    )
    draft = draft_outreach("CardCo", discovery_result, _CONTACT)
    body_lower = draft.email_body.lower()
    # Should reference the real feature...
    assert "card" in body_lower or "camera" in body_lower or "image" in body_lower
    # ...but must not claim one of the three specific risk categories AS
    # SOMETHING THIS COMPANY HAS ("your prompt injection risk") — a
    # generic mention of what AgenticGuard's business covers in general
    # ("we help teams secure against prompt injection...") is legitimate
    # copy, not a hallucinated claim about THIS target, so we only flag
    # the targeted phrasing, not the bare category name anywhere in the text.
    assert not _TARGETED_RISK_CLAIM.search(draft.email_body)


def test_case_c_is_an_explicit_honest_general_intro():
    discovery_result = DiscoveryResult(
        ai_feature="no specific AI feature identified from public site",
        risk_category="none",
        risk_rationale="No AI feature was mentioned in the scraped text.",
    )
    draft = draft_outreach("UnknownCo", discovery_result, _CONTACT)
    body_lower = draft.email_body.lower()
    # Must not fake familiarity with a specific product.
    assert "i've been following" not in body_lower
    assert "i have been following" not in body_lower
    # Must explicitly disclose that no specific feature was found —
    # this is the actual ask: honesty about being a general intro.
    assert (
        "wasn't able to find" in body_lower
        or "was not able to find" in body_lower
        or "general introduction" in body_lower
        or "couldn't find" in body_lower
        or "could not find" in body_lower
    )
    # Must not claim a risk category as something confirmed for THIS
    # company specifically (see _TARGETED_RISK_CLAIM docstring above).
    assert not _TARGETED_RISK_CLAIM.search(draft.email_body)

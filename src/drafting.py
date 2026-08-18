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
    linkedin_note=(
        "Hi — I work on AI agent security at AgenticGuard. Would love to "
        "connect and hear about your AI roadmap."
    ),
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
        try:
            result = providers.call_quality(
                system=prompts.DRAFTING_SYSTEM_PROMPT,
                user=user_prompt,
                json_mode=True,
                max_tokens=900,
            )
            start, end = result.text.find("{"), result.text.rfind("}")
            payload = json.loads(result.text[start : end + 1])
            return DraftedOutreach.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning("draft_outreach attempt %d failed: %s", attempt + 1, e)

    logger.error("draft_outreach: both attempts failed, using generic fallback")
    return _FALLBACK

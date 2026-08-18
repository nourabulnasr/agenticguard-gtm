"""
Task 4 of the brief: the reply classifier. Deliberately the smallest,
most locked-down module in the codebase — this is the anti-hallucination
core the take-home is graded on.

Guarantees enforced (see brief section "ANTI-HALLUCINATION" and the
5-step guard chain in architecture/architecture.html):
1. Only valid JSON reaches the caller — enforced by schemas.ReplyClassification,
   retried once on parse/validation failure.
2. evidence must be an exact verbatim quote proving meeting_requested=true —
   enforced structurally by ReplyClassification's model_validator, not just
   prompted for. This is the gate that survives even if the model ignores
   the system prompt.
3. proposed_time is null unless an explicit time was stated — prompted for
   (rule 3), not structurally enforceable since "was a time explicit" isn't
   checkable from the output alone.
4. Ambiguity (including soft-interest phrases like "maybe later") defaults
   to false — prompted for (rule 4); the few-shot "Let me think about it"
   example is the enforcement mechanism.
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
    """Classify a single email reply for meeting intent.

    Never raises on malformed or schema-invalid model output — worst case,
    after one retry, returns the safe all-false default (the brief's retry
    scope is "retry once on parse failure," not "retry on any failure").
    A genuine provider/network error (rate limit, connection failure) is
    NOT caught here and propagates — that's an infrastructure problem, not
    a hallucination risk, and silently returning "no meeting requested" on
    an outage would hide the failure instead of surfacing it.
    """
    user_prompt = f"Reply:\n{reply_text}"

    for attempt in range(2):  # one real attempt + one retry, per the brief
        try:
            result = providers.call_cheap(
                system=prompts.REPLY_CLASSIFIER_SYSTEM_PROMPT,
                user=user_prompt,
                json_mode=True,
                max_tokens=300,
            )
            return _extract_and_validate(result.text)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning("classify_reply attempt %d failed: %s", attempt + 1, e)

    logger.error("classify_reply: both attempts failed, returning safe default")
    return _SAFE_DEFAULT


if __name__ == "__main__":
    # Deliverable: "Test the classifier against all four cases and print
    # results" — run directly with `python -m src.reply_classifier`.
    logging.basicConfig(level=logging.WARNING)
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

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


def test_soft_interest_maybe_later_defaults_false():
    # The documented known-tradeoff case (see architecture.html): soft
    # interest is not a commitment, and under-capturing is the correct bias.
    result = classify_reply("Maybe later, let me circle back to you.")
    assert result.meeting_requested is False

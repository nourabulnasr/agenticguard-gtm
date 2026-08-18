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

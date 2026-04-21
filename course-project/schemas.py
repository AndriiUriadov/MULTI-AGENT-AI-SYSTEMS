"""
Pydantic schemas for the content-creation pipeline.

ContentPlan   — returned by the Content Strategist Agent
DraftContent  — returned by the Writer Agent
EditFeedback  — returned by the Editor Agent
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ContentPlan(BaseModel):
    """Structured content plan produced by the Strategist Agent."""

    outline: list[str] = Field(
        description="Ordered list of section/heading points the piece should cover"
    )
    keywords: list[str] = Field(
        description="Keywords/phrases the draft must include for SEO/topical coverage"
    )
    key_messages: list[str] = Field(
        description="Core messages the reader should take away"
    )
    target_audience: str = Field(
        description="Primary audience (role, seniority, channel context)"
    )
    tone: str = Field(
        description="Tone of voice — concise descriptor (e.g. 'professional, confident, inclusive')"
    )
    word_count_target: Optional[int] = Field(
        default=None,
        description=(
            "Target word count extracted from the brief (e.g. 200 if the brief says "
            "'150–220 words'). Writer must produce content within ±15% of this value. "
            "Leave as None only when the brief is silent about length."
        ),
    )


class DraftContent(BaseModel):
    """Draft article produced by the Writer Agent."""

    content: str = Field(description="Full Markdown body of the draft")
    word_count: int = Field(description="Approximate word count of content")
    keywords_used: list[str] = Field(
        description="Subset of plan keywords actually present in the draft"
    )


class EditFeedback(BaseModel):
    """Structured verdict produced by the Editor Agent."""

    verdict: Literal["APPROVED", "REVISION_NEEDED"] = Field(
        description="APPROVED if ready to publish, REVISION_NEEDED if the Writer must iterate"
    )
    issues: list[str] = Field(
        description="Specific, actionable issues to fix if REVISION_NEEDED; empty if APPROVED"
    )
    tone_score: float = Field(
        ge=0.0, le=1.0,
        description="Adherence to the requested tone (0.0 = off-brand, 1.0 = perfect match)",
    )
    accuracy_score: float = Field(
        ge=0.0, le=1.0,
        description="Factual accuracy based on fact-checking (0.0 = wrong, 1.0 = verified)",
    )
    structure_score: float = Field(
        ge=0.0, le=1.0,
        description="Adherence to plan outline and structural quality (0.0 = chaotic, 1.0 = on-plan)",
    )

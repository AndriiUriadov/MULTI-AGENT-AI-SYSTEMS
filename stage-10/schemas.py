"""
Pydantic schemas for structured agent outputs.

ResearchPlan  — returned by Planner Agent
CritiqueResult — returned by Critic Agent
"""

from typing import Literal

from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    """Structured research plan produced by the Planner Agent."""

    goal: str = Field(
        description="Clear statement of what we are trying to answer or produce"
    )
    search_queries: list[str] = Field(
        description="Specific search queries to execute (2-5 queries covering different angles)"
    )
    sources_to_check: list[Literal["knowledge_base", "web"]] = Field(
        description="Which sources to consult: 'knowledge_base', 'web', or both"
    )
    output_format: str = Field(
        description="Description of what the final report should look like"
    )


class CritiqueResult(BaseModel):
    """Structured critique produced by the Critic Agent after evaluating research findings."""

    verdict: Literal["APPROVE", "REVISE"] = Field(
        description="APPROVE if findings are sufficient, REVISE if more work is needed"
    )
    is_fresh: bool = Field(
        description="True if findings are based on up-to-date sources"
    )
    is_complete: bool = Field(
        description="True if findings fully cover the user's original request"
    )
    is_well_structured: bool = Field(
        description="True if findings are logically organized and ready for a report"
    )
    strengths: list[str] = Field(
        description="What is good about the research findings"
    )
    gaps: list[str] = Field(
        description="What is missing, outdated, or poorly covered"
    )
    revision_requests: list[str] = Field(
        description="Specific things to fix or add if verdict is REVISE; empty if APPROVE"
    )

"""Shared metric factories for homework-lesson-10 tests.

All GEval metrics use the model specified by the JUDGE_MODEL env var
(bridged in conftest.py from .env).
"""

from __future__ import annotations

import os

from deepeval.metrics import (
    AnswerRelevancyMetric,
    GEval,
    ToolCorrectnessMetric,
)
from deepeval.test_case import LLMTestCaseParams


def _model() -> str:
    return os.environ.get("JUDGE_MODEL", "gpt-4o-mini")


def plan_quality_metric(threshold: float = 0.7) -> GEval:
    return GEval(
        name="Plan Quality",
        evaluation_steps=[
            "Check that the plan contains specific, actionable search queries "
            "(not vague prompts like 'tell me about X').",
            "Check that sources_to_check is appropriate for the topic — "
            "'knowledge_base' for RAG / LangChain / LLM topics, 'web' for "
            "recent news or out-of-corpus material, both when the topic spans both.",
            "Check that output_format matches the style implied by the user's request.",
        ],
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=_model(),
        threshold=threshold,
    )


def groundedness_metric(threshold: float = 0.7) -> GEval:
    return GEval(
        name="Groundedness",
        evaluation_steps=[
            "Extract every factual claim from 'actual output'.",
            "For each claim, check if it can be directly supported by "
            "'retrieval context'.",
            "Claims not present in retrieval context count as ungrounded, "
            "even if they are factually true in general.",
            "Score = number of grounded claims / total claims.",
        ],
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        model=_model(),
        threshold=threshold,
    )


def critique_quality_metric(threshold: float = 0.7) -> GEval:
    return GEval(
        name="Critique Quality",
        evaluation_steps=[
            "Check that the critique identifies specific issues, not vague complaints.",
            "Check that revision_requests are actionable — a researcher can act on them.",
            "If verdict is APPROVE, gaps should be empty or contain only minor items.",
            "If verdict is REVISE, there must be at least one concrete revision_request.",
        ],
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=_model(),
        threshold=threshold,
    )


def correctness_metric(threshold: float = 0.6) -> GEval:
    return GEval(
        name="Correctness",
        evaluation_steps=[
            "Check whether the facts in 'actual output' contradict 'expected output'.",
            "Penalize omission of critical details present in 'expected output'.",
            "Different wording of the same concept is acceptable.",
        ],
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        model=_model(),
        threshold=threshold,
    )


def citation_presence_metric(threshold: float = 0.7) -> GEval:
    """Custom business-logic metric — Фаза 6.

    Evaluates the report's Sources/References section: it must exist, list
    at least two sources, and every listed source must actually be referenced
    somewhere in the report body (not just appended "for show").
    """
    return GEval(
        name="Citation Presence",
        evaluation_steps=[
            "Check that 'actual output' contains a '## Sources' or '## References' "
            "section (case-insensitive). If absent, score should be very low.",
            "Check that the section lists at least two distinct sources — each is "
            "either a URL (http/https) or the name of a PDF document / knowledge-base "
            "entry (e.g. 'retrieval-augmented-generation.pdf', 'langchain.pdf').",
            "For each listed source, check whether it is actually referenced in the "
            "report body — by URL, by filename, or by an inline footnote/citation "
            "marker that points at it. Sources appended without any in-text reference "
            "should reduce the score.",
            "Score reflects: (presence of section) x (>=2 sources) x (fraction of "
            "sources that are actually referenced in-body).",
        ],
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        model=_model(),
        threshold=threshold,
    )


def answer_relevancy_metric(threshold: float = 0.7) -> AnswerRelevancyMetric:
    return AnswerRelevancyMetric(threshold=threshold, model=_model())


def tool_correctness_metric(threshold: float = 0.5) -> ToolCorrectnessMetric:
    # Deterministic — no judge model; compares tool names against expected_tools.
    return ToolCorrectnessMetric(threshold=threshold)

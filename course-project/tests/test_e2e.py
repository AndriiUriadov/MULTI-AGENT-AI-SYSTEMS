"""End-to-end test: full pipeline (Strategist → auto-approve HITL → Writer ↔ Editor → save)."""

import uuid

from langgraph.types import Command

from graph import graph
from schemas import DraftContent
from tests.goldens import E2E_BRIEF, E2E_CRITERIA
from tests.judge import assert_passes, judge


def _run_pipeline_autoapprove(brief: str) -> DraftContent | None:
    """Drive the graph to completion, auto-approving the HITL plan gate."""
    config = {
        "configurable": {"thread_id": f"test-e2e-{uuid.uuid4().hex[:6]}"},
        "recursion_limit": 50,
    }

    # First pass — graph will interrupt at hitl_gate.
    for _ in graph.stream({"brief": brief, "iteration": 0}, config, stream_mode="updates"):
        pass

    # Resume with auto-approve and drive to END.
    for _ in graph.stream(Command(resume={"type": "approve"}), config, stream_mode="updates"):
        pass

    state = graph.get_state(config)
    draft_dict = state.values.get("draft") if state else None
    if draft_dict is None:
        return None
    return DraftContent.model_validate(draft_dict)


def test_end_to_end_brief_produces_publishable_content():
    draft = _run_pipeline_autoapprove(E2E_BRIEF)
    assert draft is not None, "pipeline did not produce a draft"
    # Minimum sanity check — E2E_BRIEF asks for 150–220 words, range covered by judge().
    assert draft.word_count > 100, f"final draft too short: {draft.word_count} words"
    assert draft.content.strip().startswith("#") or "##" in draft.content, (
        "final draft does not look like Markdown (no headings)"
    )

    verdict = judge(
        criteria=E2E_CRITERIA,
        input_=E2E_BRIEF,
        output=draft.content,
    )
    assert_passes(verdict, threshold=0.7)

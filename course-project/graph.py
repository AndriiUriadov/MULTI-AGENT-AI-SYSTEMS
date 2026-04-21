"""
LangGraph orchestration for the content-creation pipeline.

Layout:
    START → strategist → hitl_gate ┬─ approve → writer → editor ┬─ APPROVED / max → save → END
                                   └─ revise ─→ strategist       └─ REVISION_NEEDED → writer
Patterns: Prompt Chaining (Strategist → Writer) + HITL gate on the plan
+ Evaluator-Optimizer loop (Writer ↔ Editor, capped by max_writer_iterations).

Command API is used at the Editor node to pass both the previous draft and
the feedback back to the Writer (so it iterates, not rewrites from scratch).
"""

import re
from typing import Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agents.editor import run_editor
from agents.strategist import run_strategist
from agents.writer import run_writer
from config import Settings
from schemas import ContentPlan, DraftContent, EditFeedback
from tools import save_content

settings = Settings()


class GraphState(TypedDict, total=False):
    brief: str
    plan: Optional[dict]            # ContentPlan dumped
    plan_feedback: Optional[str]    # user feedback on plan (revise loop)
    draft: Optional[dict]           # DraftContent dumped
    feedback: Optional[dict]        # EditFeedback dumped
    iteration: int                  # writer↔editor loop counter
    final_file: Optional[str]       # path after save


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def strategist_node(state: GraphState) -> dict:
    """Run the Strategist; produces ContentPlan, respects plan_feedback on revise."""
    brief = state["brief"]
    plan_feedback = state.get("plan_feedback") or ""
    print("\n[Strategist] planning…")
    plan = run_strategist(brief, plan_feedback=plan_feedback)
    print(f"[Strategist] plan ready — outline: {len(plan.outline)} sections, "
          f"keywords: {len(plan.keywords)}, tone: {plan.tone}")
    # Reset feedback on successful replan so the next revise cycle starts clean.
    return {"plan": plan.model_dump(), "plan_feedback": None}


def hitl_gate_node(state: GraphState) -> Command:
    """Present the plan to the user; route to writer (approve) or back (revise)."""
    plan = state["plan"]
    decision = interrupt({
        "action": "approve_plan",
        "plan": plan,
    })

    if not isinstance(decision, dict):
        raise ValueError(f"HITL resume payload must be a dict, got {type(decision)}")

    dtype = decision.get("type")
    if dtype == "approve":
        print("[HITL] plan approved")
        return Command(goto="writer")
    if dtype == "revise":
        feedback = decision.get("feedback", "")
        print(f"[HITL] plan revision requested: {feedback[:100]}")
        return Command(goto="strategist", update={"plan_feedback": feedback})
    raise ValueError(f"Unknown HITL decision type: {dtype!r}")


def writer_node(state: GraphState) -> dict:
    """Produce (or revise) the draft. Picks up previous draft + editor feedback if present."""
    plan = ContentPlan.model_validate(state["plan"])
    prev_draft = DraftContent.model_validate(state["draft"]) if state.get("draft") else None
    prev_feedback = EditFeedback.model_validate(state["feedback"]) if state.get("feedback") else None

    iteration = state.get("iteration", 0) + 1
    print(f"\n[Writer] iteration {iteration}/{settings.max_writer_iterations}…")
    draft = run_writer(plan, previous_draft=prev_draft, editor_feedback=prev_feedback)
    print(f"[Writer] draft ready — {draft.word_count} words, "
          f"keywords used: {len(draft.keywords_used)}/{len(plan.keywords)}")
    return {"draft": draft.model_dump(), "iteration": iteration}


def editor_node(state: GraphState) -> Command:
    """Review the draft and route: APPROVED/max_iter → save; else → writer."""
    plan = ContentPlan.model_validate(state["plan"])
    draft = DraftContent.model_validate(state["draft"])

    print("\n[Editor] reviewing…")
    feedback = run_editor(plan, draft)
    print(f"[Editor] verdict: {feedback.verdict} — "
          f"tone={feedback.tone_score:.2f} acc={feedback.accuracy_score:.2f} "
          f"struct={feedback.structure_score:.2f}")

    iteration = state.get("iteration", 0)
    hit_cap = iteration >= settings.max_writer_iterations
    should_save = feedback.verdict == "APPROVED" or hit_cap

    if should_save:
        if hit_cap and feedback.verdict != "APPROVED":
            print(f"[Editor] max iterations ({settings.max_writer_iterations}) reached — "
                  f"saving best draft despite REVISION_NEEDED")
        return Command(goto="save", update={"feedback": feedback.model_dump()})

    print(f"[Editor] {len(feedback.issues)} issue(s) to address — looping back to Writer")
    return Command(goto="writer", update={"feedback": feedback.model_dump()})


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, max_len: int = 60) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:max_len] or "content"


def save_node(state: GraphState) -> dict:
    """Persist the approved draft to output/ as Markdown."""
    draft = DraftContent.model_validate(state["draft"])
    filename = _slug(state["brief"])
    print(f"\n[Save] writing output/{filename}.md …")
    result = save_content.invoke({"filename": filename, "content": draft.content})
    print(f"[Save] {result}")
    return {"final_file": result}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_graph():
    builder = StateGraph(GraphState)

    builder.add_node("strategist", strategist_node)
    builder.add_node("hitl_gate", hitl_gate_node)
    builder.add_node("writer", writer_node)
    builder.add_node("editor", editor_node)
    builder.add_node("save", save_node)

    builder.add_edge(START, "strategist")
    builder.add_edge("strategist", "hitl_gate")
    # hitl_gate uses Command(goto=...) — no static edge to strategist/writer.
    builder.add_edge("writer", "editor")
    # editor uses Command(goto="writer"|"save") — no static edge after it.
    builder.add_edge("save", END)

    return builder.compile(checkpointer=InMemorySaver())


graph = build_graph()

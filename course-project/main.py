"""
REPL for the content-creation pipeline.

Each user turn is wrapped in one Langfuse trace (session + user + tags
propagated). HITL interrupt after the Strategist — user approves the plan
or sends it back with feedback. Writer ↔ Editor iterate autonomously up to
max_writer_iterations before save.

Usage: python main.py
"""

import json
import logging
import os
import uuid
import warnings

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "true")

warnings.filterwarnings("ignore")
for _noisy in ("sentence_transformers", "transformers",
               "huggingface_hub", "huggingface_hub.utils._headers"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

from langfuse import get_client, observe, propagate_attributes
from langfuse.langchain import CallbackHandler
from langgraph.types import Command, Interrupt
from openai import RateLimitError

from config import Settings
from graph import graph

settings = Settings()
_lf_client = get_client()
_lf_handler = CallbackHandler()

SESSION_ID = f"course-{uuid.uuid4().hex[:8]}"
_turn_count = 0

_PLAN_PREVIEW_KEYS = ("target_audience", "tone", "outline", "key_messages", "keywords")


# ---------------------------------------------------------------------------
# HITL handler — presents the plan, asks approve / revise
# ---------------------------------------------------------------------------

def _print_plan(plan: dict) -> None:
    print("\n" + "=" * 60)
    print("📋 CONTENT PLAN — awaiting your approval")
    print("=" * 60)
    for key in _PLAN_PREVIEW_KEYS:
        value = plan.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            print(f"\n  {key}:")
            for item in value:
                print(f"    • {item}")
        else:
            print(f"\n  {key}: {value}")
    print()


def _handle_interrupt(interrupt: Interrupt) -> Command:
    """Ask the user to approve the plan or send it back with feedback."""
    value = interrupt.value or {}
    if value.get("action") == "approve_plan":
        _print_plan(value.get("plan") or {})
    else:
        print("\n" + json.dumps(value, ensure_ascii=False, indent=2))

    while True:
        choice = input("👉 approve / revise: ").strip().lower()
        if choice in ("approve", "a"):
            return Command(resume={"type": "approve"})
        if choice in ("revise", "r", "edit"):
            feedback = input("✏️  What to change: ").strip()
            if not feedback:
                print("  (feedback cannot be empty)")
                continue
            return Command(resume={"type": "revise", "feedback": feedback})
        print("  Please enter: approve / revise")


# ---------------------------------------------------------------------------
# Streaming loop — handles interrupts recursively
# ---------------------------------------------------------------------------

def _stream(inputs_or_command, config: dict) -> None:
    for chunk in graph.stream(inputs_or_command, config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            interrupt_obj = chunk["__interrupt__"][0]
            command = _handle_interrupt(interrupt_obj)
            _stream(command, config)
            return
        # Node prints are already handled inside the nodes themselves.


# ---------------------------------------------------------------------------
# Traced turn
# ---------------------------------------------------------------------------

@observe(name="content-pipeline-turn")
def _run_turn(brief: str) -> str:
    global _turn_count
    _turn_count += 1
    config = {
        "configurable": {"thread_id": f"{SESSION_ID}-t{_turn_count}"},
        "callbacks": [_lf_handler],
        "recursion_limit": 50,
    }
    with propagate_attributes(
        session_id=SESSION_ID,
        user_id=settings.langfuse_user_id,
        tags=["course-project", "content-pipeline"],
    ):
        _stream({"brief": brief, "iteration": 0}, config)

    state = graph.get_state(config)
    final = state.values.get("final_file") if state else None
    return final or ""


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

def _warmup() -> None:
    """Eagerly load the reranker so the first HITL approval isn't blocked by it."""
    from retriever import get_retriever
    try:
        get_retriever()
    except Exception:
        pass


def main() -> None:
    print("=" * 60)
    print("  Content Creation Pipeline  (course project)")
    print(f"  Langfuse session: {SESSION_ID}")
    print("  Enter a brief (topic, audience, channel, tone, word count).")
    print("  Type 'quit' or 'exit' to stop.")
    print("=" * 60)

    print("  Loading retriever model…", end=" ", flush=True)
    _warmup()
    print("ready.")

    try:
        while True:
            try:
                brief = input("\nBrief: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nBye!")
                break

            if not brief:
                continue
            if brief.lower() in ("quit", "exit", "q"):
                print("Bye!")
                break

            import sys
            if not sys.stdin.isatty():
                print(brief)

            try:
                _run_turn(brief)
            except RateLimitError as e:
                print("\n[⏸️  OpenAI rate limit — wait ~1 minute and try again]")
                print(f"  Detail: {e}")
            _lf_client.flush()
    finally:
        _lf_client.flush()


if __name__ == "__main__":
    main()

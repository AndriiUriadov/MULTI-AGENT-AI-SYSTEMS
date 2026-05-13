"""
REPL for the multi-agent research system (homework-lesson-12).

Streams the Supervisor Agent, handles HITL interrupts for save_report,
and supports approve / edit / reject decisions. Every user turn is wrapped
in one Langfuse trace (with session + user + tags propagated).

Usage: python main.py
"""

import json
import logging
import os
import uuid
import warnings

# Must be set before any HF/transformers imports to suppress loading noise.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "true")

warnings.filterwarnings("ignore")

for _noisy_logger in ("sentence_transformers", "transformers",
                      "huggingface_hub", "huggingface_hub.utils._headers"):
    logging.getLogger(_noisy_logger).setLevel(logging.ERROR)

from langchain_core.messages import AIMessage, ToolMessage
from langfuse import get_client, observe, propagate_attributes
from langfuse.langchain import CallbackHandler
from langgraph.types import Command, Interrupt
from openai import RateLimitError

from config import Settings
from supervisor import supervisor

settings = Settings()
_lf_client = get_client()
_lf_handler = CallbackHandler()

# One Langfuse session groups every turn of this REPL run. Each turn gets its
# own thread_id so the supervisor starts with a clean message history per
# query (prevents research-count accumulation and trims token usage).
SESSION_ID = f"hw12-{uuid.uuid4().hex[:8]}"
_turn_count = 0

_PREVIEW_LEN = 400  # chars of report content to preview before approve/edit/reject

# Tools that the HITL handler displays — skip their tool-call lines to avoid
# showing the same call twice (once pre-interrupt, once post-resume).
_HITL_TOOLS = {"save_report"}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_tool_calls(msg: AIMessage) -> None:
    for tc in msg.tool_calls:
        if tc["name"] in _HITL_TOOLS:
            continue  # shown by the HITL UI instead
        args_str = json.dumps(tc["args"], ensure_ascii=False)
        if len(args_str) > 200:
            args_str = args_str[:200] + "…"
        print(f"  🔧 {tc['name']}({args_str})")


def _print_tool_results(messages: list) -> None:
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        content = str(msg.content)
        preview = content[:200] + ("…" if len(content) > 200 else "")
        print(f"  📎 [{msg.name}] {preview}")


def _print_step(node: str, update: dict) -> None:
    """Print one streaming step from the supervisor graph."""
    msgs = update.get("messages", [])
    if not msgs:
        return

    for msg in msgs:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                _print_tool_calls(msg)
            elif msg.content:
                # Final answer from supervisor
                print(f"\nAgent: {msg.content}")
        elif isinstance(msg, ToolMessage):
            _print_tool_results([msg])


# ---------------------------------------------------------------------------
# HITL interrupt handler
# ---------------------------------------------------------------------------

def _handle_interrupt(interrupt: Interrupt) -> Command:
    """Show the pending action and ask the user to approve / edit / reject."""
    action_requests = interrupt.value.get("action_requests", [])

    print("\n" + "=" * 60)
    print("⏸️  ACTION REQUIRES APPROVAL")
    print("=" * 60)

    for req in action_requests:
        tool_name = req.get("name", "unknown")
        args = req.get("args", {})
        print(f"  Tool: {tool_name}")
        if tool_name == "save_report":
            print(f"  File: {args.get('filename', '?')}.md")
            content = str(args.get("content", ""))
            preview = content[:_PREVIEW_LEN]
            if len(content) > _PREVIEW_LEN:
                preview += "\n  …"
            print(f"\n  --- Report preview ---\n{preview}\n  ---")
        else:
            print(f"  Args: {json.dumps(args, ensure_ascii=False)[:300]}")

    print()

    while True:
        decision = input("👉 approve / edit / reject: ").strip().lower()

        if decision == "approve":
            return Command(
                resume={interrupt.id: {"decisions": [{"type": "approve"}]}}
            )

        elif decision == "edit":
            feedback = input("✏️  Your feedback: ").strip()
            if not feedback:
                print("  (feedback cannot be empty, try again)")
                continue
            # "edit" means: reject the current report and ask the supervisor to
            # revise it based on the feedback, then present a new HITL prompt.
            return Command(
                resume={
                    interrupt.id: {
                        "decisions": [
                            {
                                "type": "reject",
                                "message": f"Please revise the report: {feedback}",
                            }
                        ]
                    }
                }
            )

        elif decision == "reject":
            reason = input("🚫 Reason (optional): ").strip() or "User rejected"
            return Command(
                resume={
                    interrupt.id: {
                        "decisions": [{"type": "reject", "message": reason}]
                    }
                }
            )

        else:
            print("  Please enter: approve / edit / reject")


# ---------------------------------------------------------------------------
# Streaming loop
# ---------------------------------------------------------------------------

def _stream(inputs_or_command, config: dict) -> None:
    """Stream the supervisor, handling HITL interrupts recursively."""
    for chunk in supervisor.stream(inputs_or_command, config):

        if "__interrupt__" in chunk:
            interrupt = chunk["__interrupt__"][0]
            command = _handle_interrupt(interrupt)
            _stream(command, config)
            return

        for node, update in chunk.items():
            if node.startswith("__"):
                continue
            if isinstance(update, dict):
                _print_step(node, update)


# ---------------------------------------------------------------------------
# Traced turn — one user input → one Langfuse trace
# ---------------------------------------------------------------------------

@observe(name="supervisor-turn")
def _run_turn(user_input: str) -> str:
    """Stream one turn inside a Langfuse trace; return the final assistant text."""
    global _turn_count
    _turn_count += 1
    turn_config = {
        "configurable": {"thread_id": f"{SESSION_ID}-t{_turn_count}"},
        "callbacks": [_lf_handler],
    }
    with propagate_attributes(
        session_id=SESSION_ID,
        user_id=settings.langfuse_user_id,
        tags=["hw-12", "multi-agent", "supervisor"],
    ):
        _stream(
            {"messages": [{"role": "user", "content": user_input}]},
            turn_config,
        )

    # Pull the most recent assistant reply from supervisor state so Langfuse
    # records it as the trace output (evaluators bind to {{output}}).
    state = supervisor.get_state(turn_config)
    msgs = state.values.get("messages", []) if state else []
    for msg in reversed(msgs):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return ""


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

def _warmup() -> None:
    """Pre-load the reranker model before the REPL starts."""
    from retriever import get_retriever
    try:
        get_retriever()
    except Exception:
        pass  # index may not exist; retriever will fail gracefully later


def main() -> None:
    print("=" * 60)
    print("  Multi-Agent Research System  (homework-lesson-12)")
    print(f"  Langfuse session: {SESSION_ID}")
    print("  Type 'quit' or 'exit' to stop.")
    print("=" * 60)

    print("  Loading retriever model…", end=" ", flush=True)
    _warmup()
    print("ready.")

    try:
        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nBye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Bye!")
                break

            # When input is piped (non-interactive), echo the query for readable logs.
            import sys as _sys
            if not _sys.stdin.isatty():
                print(user_input)

            print()
            try:
                _run_turn(user_input)
            except RateLimitError as e:
                print("\n[⏸️  OpenAI rate limit reached — wait ~1 minute and try again]")
                print(f"  Detail: {e}")
            _lf_client.flush()
    finally:
        _lf_client.flush()


if __name__ == "__main__":
    main()

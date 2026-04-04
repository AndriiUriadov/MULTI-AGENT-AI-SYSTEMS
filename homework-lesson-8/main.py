"""
REPL for the multi-agent research system (homework-lesson-8).

Streams the Supervisor Agent, handles HITL interrupts for save_report,
and supports approve / edit / reject decisions.

Usage: python main.py
"""

import json

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, Interrupt

from supervisor import supervisor

# Fixed thread_id gives the supervisor memory across turns in a session.
_CONFIG = {"configurable": {"thread_id": "session-1"}}

_PREVIEW_LEN = 400  # chars of report content to preview before approve/edit/reject


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_tool_calls(msg: AIMessage) -> None:
    for tc in msg.tool_calls:
        args_str = json.dumps(tc["args"], ensure_ascii=False)
        # Trim long args for readability
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

    # Display all pending tool calls (usually just save_report)
    for req in action_requests:
        tool_name = req.get("name", "unknown")
        args = req.get("args", {})
        print(f"  Tool: {tool_name}")
        if tool_name == "save_report":
            print(f"  File: {args.get('filename', '?')}.md")
            content_preview = str(args.get("content", ""))[:_PREVIEW_LEN]
            if len(str(args.get("content", ""))) > _PREVIEW_LEN:
                content_preview += "\n  …"
            print(f"\n  --- Report preview ---\n{content_preview}\n  ---")
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
            return Command(
                resume={
                    interrupt.id: {
                        "decisions": [
                            {
                                "type": "edit",
                                "edited_action": {"feedback": feedback},
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
            # HITL interrupt — ask user and resume
            interrupt = chunk["__interrupt__"][0]
            command = _handle_interrupt(interrupt)
            _stream(command, config)
            return

        # Normal graph update — print messages
        for node, update in chunk.items():
            if node.startswith("__"):
                continue
            if isinstance(update, dict):
                _print_step(node, update)


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  Multi-Agent Research System  (homework-lesson-8)")
    print("  Type 'quit' or 'exit' to stop.")
    print("=" * 60)

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

        print()
        _stream(
            {"messages": [{"role": "user", "content": user_input}]},
            _CONFIG,
        )


if __name__ == "__main__":
    main()

"""
REPL for the multi-agent research system (homework-lesson-9).

Starts MCP and ACP servers in background threads, then runs the
Supervisor Agent with HITL interrupts for save_report.

Usage: python main.py
"""

import asyncio
import json
import logging
import os
import threading
import time
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
from langgraph.types import Command, Interrupt

from config import ACP_PORT, REPORT_MCP_PORT, SEARCH_MCP_PORT
from supervisor import supervisor

_CONFIG = {"configurable": {"thread_id": "session-1"}}
_PREVIEW_LEN = 400
_HITL_TOOLS = {"save_report"}


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

def _start_servers() -> None:
    """Start SearchMCP, ReportMCP, and ACP server in background threads."""

    # SearchMCP
    from mcp_servers.search_mcp import mcp as search_mcp
    def _run_search():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            search_mcp.run_async(transport="streamable-http", host="127.0.0.1", port=SEARCH_MCP_PORT)
        )
    threading.Thread(target=_run_search, daemon=True, name="SearchMCP").start()

    # ReportMCP
    from mcp_servers.report_mcp import mcp as report_mcp
    def _run_report():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            report_mcp.run_async(transport="streamable-http", host="127.0.0.1", port=REPORT_MCP_PORT)
        )
    threading.Thread(target=_run_report, daemon=True, name="ReportMCP").start()

    # ACP Server
    from acp_server import server as acp_server
    def _run_acp():
        acp_server.run(port=ACP_PORT)
    threading.Thread(target=_run_acp, daemon=True, name="ACPServer").start()

    time.sleep(3)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_tool_calls(msg: AIMessage) -> None:
    for tc in msg.tool_calls:
        if tc["name"] in _HITL_TOOLS:
            continue
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
    msgs = update.get("messages", [])
    if not msgs:
        return
    for msg in msgs:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                _print_tool_calls(msg)
            elif msg.content:
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
# REPL
# ---------------------------------------------------------------------------

def _warmup() -> None:
    """Pre-load the reranker model before the REPL starts."""
    from retriever import get_retriever
    try:
        get_retriever()
    except Exception:
        pass


def main() -> None:
    print("=" * 60)
    print("  Multi-Agent Research System  (homework-lesson-9)")
    print("  MCP + ACP architecture")
    print("  Type 'quit' or 'exit' to stop.")
    print("=" * 60)

    print("  Starting MCP servers and ACP server…", end=" ", flush=True)
    _start_servers()
    print("ready.")

    print("  Loading retriever model…", end=" ", flush=True)
    _warmup()
    print("ready.")

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

        import sys as _sys
        if not _sys.stdin.isatty():
            print(user_input)

        print()
        _stream(
            {"messages": [{"role": "user", "content": user_input}]},
            _CONFIG,
        )


if __name__ == "__main__":
    main()

"""
Supervisor Agent — orchestrates Plan → Research → Critique → Save cycle.

Sub-agents are called via ACP (acp_server.py).
save_report is called via ReportMCP.
All async calls are wrapped in asyncio.run() to keep Supervisor synchronous,
which preserves HumanInTheLoopMiddleware + InMemorySaver HITL behaviour.
"""

import asyncio
import json

from acp_sdk.client import Client as ACPClient
from acp_sdk.models import Message, MessagePart
from fastmcp import Client as MCPClient
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from config import (
    ACP_BASE_URL,
    REPORT_MCP_URL,
    SUPERVISOR_PROMPT,
    Settings,
)

settings = Settings()

_ACP_HEADERS = {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

async def _acp_call(agent_name: str, text: str) -> str:
    """Call an ACP agent and return its text response."""
    async with ACPClient(base_url=ACP_BASE_URL, headers=_ACP_HEADERS) as client:
        run = await client.run_sync(
            agent=agent_name,
            input=[Message(role="user", parts=[MessagePart(content=text)])],
        )
    if not run.output:
        return f"[{agent_name} returned no output]"
    return run.output[-1].parts[0].content


async def _mcp_save(filename: str, content: str) -> str:
    """Call save_report on ReportMCP and return the result."""
    async with MCPClient(REPORT_MCP_URL) as client:
        result = await client.call_tool("save_report", {"filename": filename, "content": content})
    return str(result.data)


# ---------------------------------------------------------------------------
# Supervisor @tools — sync wrappers around async ACP/MCP calls
# ---------------------------------------------------------------------------

@tool
def delegate_to_planner(request: str) -> str:
    """Decompose a research request into a structured plan.

    Delegates to the Planner Agent via ACP. Returns a ResearchPlan JSON with
    goal, search_queries, sources_to_check, and output_format.
    Always call this first before delegate_to_researcher().
    """
    print(f"  🤖 [planner via ACP] ← {request[:80]}…" if len(request) > 80 else f"  🤖 [planner via ACP] ← {request}")
    result = asyncio.run(_acp_call("planner", request))
    return result


@tool
def delegate_to_researcher(request: str, runtime: ToolRuntime) -> str:
    """Execute research using web search and the local knowledge base.

    Delegates to the Research Agent via ACP. The request MUST be a plain-text
    instruction — not raw JSON. Describe what to research and which sources to use.
    Maximum revision rounds enforced automatically.
    """
    # Count prior researcher calls to enforce revision limit
    messages = runtime.state.get("messages", [])
    research_calls = sum(
        1 for m in messages
        if isinstance(m, ToolMessage) and m.name == "delegate_to_researcher"
    )
    if research_calls >= settings.max_revisions + 1:
        return (
            f"[REVISION LIMIT REACHED — {research_calls} research rounds completed] "
            f"You have used all {settings.max_revisions} allowed revision rounds. "
            f"You MUST now call save_report() with the best findings gathered. "
            f"Do NOT call delegate_to_researcher() again."
        )

    print(f"  🤖 [researcher via ACP] ← {request[:80]}…" if len(request) > 80 else f"  🤖 [researcher via ACP] ← {request}")
    result = asyncio.run(_acp_call("researcher", request))
    return result


@tool
def delegate_to_critic(findings: str) -> str:
    """Evaluate research findings and return a structured verdict.

    Delegates to the Critic Agent via ACP. Returns a CritiqueResult JSON with
    verdict (APPROVE/REVISE), is_fresh, is_complete, is_well_structured,
    strengths, gaps, and revision_requests.
    """
    # Sanitize and truncate to avoid API context errors
    cleaned = "".join(c for c in findings if c >= " " or c in "\n\t")
    if len(cleaned) > 6000:
        cleaned = cleaned[:6000] + "\n\n[...truncated for review...]"

    print("  🤖 [critic via ACP]")
    result = asyncio.run(_acp_call("critic", cleaned))
    return result


@tool
def save_report(filename: str, content: str) -> str:
    """Save the final Markdown report to disk via ReportMCP.

    This is a write operation — it requires human approval before executing.
    filename: short name without extension (e.g. 'rag_comparison').
    content: complete Markdown report with title, sections, and Sources.
    """
    result = asyncio.run(_mcp_save(filename, content))
    return result


# ---------------------------------------------------------------------------
# Supervisor Agent
# ---------------------------------------------------------------------------

_model = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

supervisor = create_agent(
    _model,
    tools=[delegate_to_planner, delegate_to_researcher, delegate_to_critic, save_report],
    system_prompt=SUPERVISOR_PROMPT,
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={"save_report": True},
            description_prefix="📄 Report requires your approval before saving",
        ),
    ],
    checkpointer=InMemorySaver(),
)

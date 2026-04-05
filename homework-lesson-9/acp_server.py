"""
ACP Server — exposes three agents (planner, researcher, critic) via ACP protocol.

Each agent handler:
  1. Opens a fastmcp.Client connection to SearchMCP
  2. Converts MCP tools to LangChain format via mcp_tools_to_langchain
  3. Builds agent via build_*() and calls ainvoke()
  4. Returns Message(role="agent", parts=[MessagePart(content=...)])

Port: 8903 (ACP_PORT from config)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acp_sdk.models import Message, MessagePart
from acp_sdk.server import Server
from fastmcp import Client
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.messages import AIMessage, ToolMessage

from agents.critic import build_critic
from agents.planner import build_planner
from agents.research import build_researcher
from config import ACP_PORT, SEARCH_MCP_URL, Settings
from mcp_utils import mcp_tools_to_langchain
from schemas import CritiqueResult

settings = Settings()

server = Server()

# Recursion limits (same rationale as hw8)
_PLANNER_RECURSION = settings.max_iterations * 2 + 1
_RESEARCHER_RECURSION = settings.max_iterations * 2 + 1
_CRITIC_RECURSION = 31

_CRITIC_REVISE_FALLBACK = CritiqueResult(
    verdict="REVISE",
    is_fresh=False,
    is_complete=False,
    is_well_structured=True,
    strengths=[],
    gaps=["Critic could not produce a structured verdict — assuming revision needed."],
    revision_requests=["Re-evaluate findings and produce a complete structured report."],
)

_MAX_FINDINGS_LEN = 6000


def _print_tool_calls(result: dict, indent: str = "    ") -> None:
    """Print tool calls from agent message history (sub-agent level)."""
    for msg in result.get("messages", []):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                args_str = json.dumps(tc["args"], ensure_ascii=False)
                if len(args_str) > 120:
                    args_str = args_str[:120] + "…"
                print(f"{indent}🔧 {tc['name']}({args_str})")
        elif isinstance(msg, ToolMessage):
            preview = str(msg.content)[:120]
            if len(str(msg.content)) > 120:
                preview += "…"
            print(f"{indent}📎 [{msg.name}] {preview}")


# ---------------------------------------------------------------------------
# Planner agent handler
# ---------------------------------------------------------------------------

@server.agent(
    name="planner",
    description="Decomposes a research request into a structured ResearchPlan.",
)
async def planner_handler(input: list[Message]) -> Message:
    user_text = input[-1].parts[0].content

    async with Client(SEARCH_MCP_URL) as mcp_client:
        mcp_tools = await mcp_client.list_tools()
        lc_tools = mcp_tools_to_langchain(mcp_tools, mcp_client)
        agent = build_planner(lc_tools)

        result = await agent.ainvoke(
            {"messages": [("user", user_text)]},
            config={"recursion_limit": _PLANNER_RECURSION},
        )

    _print_tool_calls(result)
    plan = result["structured_response"]
    return Message(role="agent", parts=[MessagePart(content=plan.model_dump_json(indent=2))])


# ---------------------------------------------------------------------------
# Researcher agent handler
# ---------------------------------------------------------------------------

@server.agent(
    name="researcher",
    description="Executes a research plan using web search and the local knowledge base.",
)
async def researcher_handler(input: list[Message]) -> Message:
    user_text = input[-1].parts[0].content

    async with Client(SEARCH_MCP_URL) as mcp_client:
        mcp_tools = await mcp_client.list_tools()
        lc_tools = mcp_tools_to_langchain(mcp_tools, mcp_client)
        agent = build_researcher(lc_tools)

        result = await agent.ainvoke(
            {"messages": [("user", user_text)]},
            config={"recursion_limit": _RESEARCHER_RECURSION},
        )

    _print_tool_calls(result)
    findings = result["messages"][-1].content
    return Message(role="agent", parts=[MessagePart(content=findings)])


# ---------------------------------------------------------------------------
# Critic agent handler
# ---------------------------------------------------------------------------

@server.agent(
    name="critic",
    description="Evaluates research findings for freshness, completeness, and structure.",
)
async def critic_handler(input: list[Message]) -> Message:
    findings = input[-1].parts[0].content

    # Sanitize and truncate to avoid API context errors
    cleaned = "".join(c for c in findings if c >= " " or c in "\n\t")
    if len(cleaned) > _MAX_FINDINGS_LEN:
        cleaned = cleaned[:_MAX_FINDINGS_LEN] + "\n\n[...truncated for review...]"

    try:
        async with Client(SEARCH_MCP_URL) as mcp_client:
            mcp_tools = await mcp_client.list_tools()
            lc_tools = mcp_tools_to_langchain(mcp_tools, mcp_client)
            agent = build_critic(lc_tools)

            result = await agent.ainvoke(
                {"messages": [("user", cleaned)]},
                config={"recursion_limit": _CRITIC_RECURSION},
            )

        _print_tool_calls(result)
        critique = result["structured_response"]

    except StructuredOutputValidationError:
        print("    📎 [critique] (structured parse failed — defaulting to REVISE)")
        critique = _CRITIC_REVISE_FALLBACK

    return Message(role="agent", parts=[MessagePart(content=critique.model_dump_json(indent=2))])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.run(port=ACP_PORT)

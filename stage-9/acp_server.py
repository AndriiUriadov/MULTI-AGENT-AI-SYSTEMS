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

# Recursion limits — planner/researcher need headroom for multiple tool calls
_PLANNER_RECURSION = 51
_RESEARCHER_RECURSION = 51
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

def _sanitize(text: str, max_len: int = 0) -> str:
    """Remove control characters and optionally truncate."""
    cleaned = "".join(c for c in text if c >= " " or c in "\n\t")
    if max_len and len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "\n\n[...truncated...]"
    return cleaned


async def _invoke_agent(build_fn, user_text: str, recursion_limit: int) -> dict:
    """Open SearchMCP, build agent via build_fn, invoke, return result dict."""
    async with Client(SEARCH_MCP_URL) as mcp_client:
        lc_tools = mcp_tools_to_langchain(await mcp_client.list_tools(), mcp_client)
        return await build_fn(lc_tools).ainvoke(
            {"messages": [("user", user_text)]},
            config={"recursion_limit": recursion_limit},
        )


@server.agent(
    name="planner",
    description="Decomposes a research request into a structured ResearchPlan.",
)
async def planner_handler(input: list[Message]) -> Message:
    user_text = _sanitize(input[-1].parts[0].content)
    result = await _invoke_agent(build_planner, user_text, _PLANNER_RECURSION)
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
    user_text = _sanitize(input[-1].parts[0].content, max_len=8000)
    result = await _invoke_agent(build_researcher, user_text, _RESEARCHER_RECURSION)
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
    cleaned = _sanitize(input[-1].parts[0].content, max_len=_MAX_FINDINGS_LEN)

    try:
        result = await _invoke_agent(build_critic, cleaned, _CRITIC_RECURSION)
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

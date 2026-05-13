"""
Critic Agent — independently verifies research findings and returns a verdict.

Exposed:
    critic_agent  — compiled LangGraph agent (create_agent with response_format)
    run_critic(findings) → CritiqueResult
"""

import json

from langchain.agents import create_agent
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from openai import RateLimitError

from config import Settings, load_prompt
from schemas import CritiqueResult
from tools import knowledge_search, read_url, web_search

settings = Settings()

_model = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

critic_agent = create_agent(
    _model,
    tools=[web_search, read_url, knowledge_search],
    system_prompt=load_prompt("critic_system"),
    response_format=CritiqueResult,
)

# Critic is capped at 4 tool calls in its prompt, but allow headroom.
_RECURSION = 31

_REVISE_FALLBACK = CritiqueResult(
    verdict="REVISE",
    is_fresh=False,
    is_complete=False,
    is_well_structured=True,
    strengths=[],
    gaps=["Critic could not produce a structured verdict — assuming revision needed."],
    revision_requests=["Re-evaluate findings and produce a complete structured report."],
)


def run_critic(findings: str) -> CritiqueResult:
    """Invoke the Critic Agent, print verification tool calls, return CritiqueResult."""
    try:
        result = critic_agent.invoke(
            {"messages": [{"role": "user", "content": findings}]},
            config={"recursion_limit": _RECURSION},
        )
    except StructuredOutputValidationError:
        print("    📎 [critique] (structured parse failed — defaulting to REVISE)")
        return _REVISE_FALLBACK
    except GraphRecursionError:
        print("    📎 [critique] (recursion limit reached — defaulting to REVISE)")
        return _REVISE_FALLBACK
    except RateLimitError:
        print("    📎 [critique] (OpenAI rate limit — defaulting to REVISE)")
        return _REVISE_FALLBACK

    # Print tool calls from message history
    for msg in result.get("messages", []):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                args_str = json.dumps(tc["args"], ensure_ascii=False)
                if len(args_str) > 120:
                    args_str = args_str[:120] + "…"
                print(f"    🔧 {tc['name']}({args_str})")  # indented — sub-agent
        elif isinstance(msg, ToolMessage):
            preview = str(msg.content)[:120]
            if len(str(msg.content)) > 120:
                preview += "…"
            print(f"    📎 [{msg.name}] {preview}")
    return result["structured_response"]

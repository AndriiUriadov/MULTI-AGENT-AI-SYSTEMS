"""
Planner Agent — decomposes a user request into a structured ResearchPlan.

Exposed:
    planner_agent  — compiled LangGraph agent (create_agent with response_format)
    run_planner(request) → ResearchPlan
"""

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from config import Settings, PLANNER_PROMPT
from schemas import ResearchPlan
from tools import knowledge_search, web_search

settings = Settings()

_model = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

planner_agent = create_agent(
    _model,
    tools=[web_search, knowledge_search],
    system_prompt=PLANNER_PROMPT,
    response_format=ResearchPlan,
)

_RECURSION = settings.max_iterations * 2 + 1


def run_planner(request: str) -> ResearchPlan:
    """Invoke the Planner Agent, print sub-agent tool calls, return ResearchPlan."""
    result = planner_agent.invoke(
        {"messages": [{"role": "user", "content": request}]},
        config={"recursion_limit": _RECURSION},
    )
    # Print tool calls from message history
    for msg in result.get("messages", []):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                args_str = json.dumps(tc["args"], ensure_ascii=False)
                if len(args_str) > 120:
                    args_str = args_str[:120] + "…"
                print(f"    🔧 {tc['name']}({args_str})")
        elif isinstance(msg, ToolMessage):
            preview = str(msg.content)[:120]
            if len(str(msg.content)) > 120:
                preview += "…"
            print(f"    📎 [{msg.name}] {preview}")
    return result["structured_response"]

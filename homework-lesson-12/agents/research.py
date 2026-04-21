"""
Research Agent — executes a research plan using web and knowledge base tools.

Exposed:
    researcher_agent  — compiled LangGraph agent
    run_researcher(request) → str  (Markdown findings text)
"""

import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from config import Settings, load_prompt
from tools import knowledge_search, read_url, web_search

settings = Settings()

_model = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

researcher_agent = create_agent(
    _model,
    tools=[web_search, read_url, knowledge_search],
    system_prompt=load_prompt("researcher_system"),
)

_RECURSION = settings.max_iterations * 2 + 1


def run_researcher(request: str) -> str:
    """Invoke the Research Agent, print sub-agent tool calls, return findings."""
    result = researcher_agent.invoke(
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
    return result["messages"][-1].content

"""
Content Strategist Agent — turns a brief into a structured ContentPlan.

Tools: web_search (trends, competitors), knowledge_search (brand RAG).
System prompt: Langfuse prompt `strategist_system` with template variable
`plan_feedback` (empty on first run, user-provided on revise loop).
"""

import json

from langchain.agents import create_agent
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from openai import RateLimitError

from config import Settings, load_prompt
from model_gateway import get_chat_model
from schemas import ContentPlan
from tools import knowledge_search, read_url, web_search

settings = Settings()

_RECURSION = 51  # room for ~25 tool calls (prompt budgets fewer, but tool errors trigger retries)


def _fallback_plan(brief: str) -> ContentPlan:
    """Conservative plan used when the Strategist agent fails to return structured output.

    The plan is intentionally generic so it does not lie about having done
    research. The user will see it at the HITL gate and can either approve or
    ask for a proper replan.
    """
    return ContentPlan(
        outline=[
            "Вступ: контекст і значення теми",
            "Основна частина 1: ключовий факт / досягнення",
            "Основна частина 2: деталі та учасники",
            "Основна частина 3: значення для аудиторії",
            "Заклик до дії або запрошення",
        ],
        keywords=["КПІ ім. Ігоря Сікорського"],
        key_messages=["Fallback plan — Strategist agent failed to produce a structured ContentPlan."],
        target_audience="Відповідно до брифу (агент не зміг уточнити)",
        tone="Відповідно до брифу",
    )


def _build_agent(plan_feedback: str = ""):
    return create_agent(
        get_chat_model("strategist", temperature=0.2),
        tools=[web_search, read_url, knowledge_search],
        system_prompt=load_prompt(
            "strategist_system",
            plan_feedback=plan_feedback or "(no prior feedback — this is the first attempt)",
        ),
        response_format=ContentPlan,
    )


def _print_tool_trace(messages: list) -> None:
    for msg in messages:
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


def run_strategist(brief: str, plan_feedback: str = "") -> ContentPlan:
    """Invoke the Strategist, print tool calls, return a ContentPlan.

    Falls back to a conservative generic plan if the agent cannot produce a
    structured ContentPlan (recursion limit hit, rate limit, parse failure).
    """
    agent = _build_agent(plan_feedback=plan_feedback)
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": brief}]},
            config={"recursion_limit": _RECURSION},
        )
    except StructuredOutputValidationError:
        print("    📎 [strategist] (structured parse failed — fallback plan)")
        return _fallback_plan(brief)
    except GraphRecursionError:
        print("    📎 [strategist] (recursion limit reached — fallback plan)")
        return _fallback_plan(brief)
    except RateLimitError:
        print("    📎 [strategist] (OpenAI rate limit — fallback plan)")
        return _fallback_plan(brief)

    _print_tool_trace(result.get("messages", []))
    return result["structured_response"]

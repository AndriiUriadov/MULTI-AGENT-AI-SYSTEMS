"""
Editor Agent — reviews DraftContent against the plan and returns EditFeedback.

Tools: web_search, read_url (fact-check).
Template vars: plan_json (the original approved plan).
"""

import json

from langchain.agents import create_agent
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from openai import RateLimitError

from config import Settings, load_prompt
from model_gateway import get_chat_model
from schemas import ContentPlan, DraftContent, EditFeedback
from tools import read_url, web_search

settings = Settings()

_RECURSION = 51  # room for ~25 tool calls; prompt budgets 3, but bad drafts can trigger retries

# Conservative fallback: if the Editor fails to produce a structured verdict,
# treat it as REVISION_NEEDED so the pipeline either improves the draft or
# exits via the max_writer_iterations cap — never a silent APPROVED.
_REVISE_FALLBACK = EditFeedback(
    verdict="REVISION_NEEDED",
    issues=["Editor could not produce a structured verdict; please revise conservatively."],
    tone_score=0.5,
    accuracy_score=0.5,
    structure_score=0.5,
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


def run_editor(plan: ContentPlan, draft: DraftContent) -> EditFeedback:
    """Review the draft and return a structured EditFeedback verdict."""
    system_prompt = load_prompt(
        "editor_system",
        plan_json=plan.model_dump_json(indent=2),
    )
    agent = create_agent(
        get_chat_model("editor", temperature=0.0),
        tools=[web_search, read_url],
        system_prompt=system_prompt,
        response_format=EditFeedback,
    )

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": draft.content}]},
            config={"recursion_limit": _RECURSION},
        )
    except StructuredOutputValidationError:
        print("    📎 [editor] (structured parse failed — REVISION_NEEDED fallback)")
        return _REVISE_FALLBACK
    except GraphRecursionError:
        print("    📎 [editor] (recursion limit reached — REVISION_NEEDED fallback)")
        return _REVISE_FALLBACK
    except RateLimitError:
        print("    📎 [editor] (OpenAI rate limit — REVISION_NEEDED fallback)")
        return _REVISE_FALLBACK

    _print_tool_trace(result.get("messages", []))
    return result["structured_response"]

"""
Writer Agent — turns a ContentPlan into a DraftContent.

Tools: web_search, read_url (facts & stats).
Template vars: plan (JSON), previous_draft, editor_feedback (empty on first run).
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

_RECURSION = 51


def _fallback_draft(plan: ContentPlan) -> DraftContent:
    """Minimal draft when the Writer agent fails to return structured output.

    Produced only from the plan (no web research) so the pipeline can proceed
    to the Editor, which will mark it REVISION_NEEDED and trigger an iteration.
    """
    parts = [f"# {plan.outline[0] if plan.outline else 'Матеріал'}\n"]
    for section in plan.outline:
        parts.append(f"\n## {section}\n\n(Розділ потребує наповнення.)\n")
    content = "".join(parts)
    return DraftContent(
        content=content,
        word_count=len(content.split()),
        keywords_used=[],
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


def run_writer(
    plan: ContentPlan,
    previous_draft: DraftContent | None = None,
    editor_feedback: EditFeedback | None = None,
) -> DraftContent:
    """Invoke the Writer Agent.

    On the first pass previous_draft and editor_feedback are None. On revision
    loops the agent receives both so it can iterate, not rewrite from scratch.
    """
    system_prompt = load_prompt(
        "writer_system",
        plan_json=plan.model_dump_json(indent=2),
        previous_draft=(previous_draft.content if previous_draft else "(no prior draft)"),
        editor_feedback=(
            editor_feedback.model_dump_json(indent=2)
            if editor_feedback
            else "(no prior feedback — this is the first draft)"
        ),
    )
    agent = create_agent(
        get_chat_model("writer", temperature=0.5),
        tools=[web_search, read_url],
        system_prompt=system_prompt,
        response_format=DraftContent,
    )

    # The user-message content is intentionally terse; all state lives in the
    # system prompt so the agent's tool-call behavior is deterministic.
    user_msg = (
        "Write the draft now. Follow the plan in the system prompt. "
        "If there is editor feedback, address every issue."
    )
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_msg}]},
            config={"recursion_limit": _RECURSION},
        )
    except StructuredOutputValidationError:
        print("    📎 [writer] (structured parse failed — fallback draft)")
        return _fallback_draft(plan)
    except GraphRecursionError:
        print("    📎 [writer] (recursion limit reached — fallback draft)")
        return _fallback_draft(plan)
    except RateLimitError:
        print("    📎 [writer] (OpenAI rate limit — fallback draft)")
        return _fallback_draft(plan)

    _print_tool_trace(result.get("messages", []))
    return result["structured_response"]

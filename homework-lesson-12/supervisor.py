"""
Supervisor Agent — orchestrates the Plan → Research → Critique → Save cycle.

Wraps the three sub-agents as @tool functions and creates the top-level agent
with HumanInTheLoopMiddleware gating save_report.

Exposed:
    supervisor  — compiled LangGraph agent (with HITL + InMemorySaver)
"""

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from agents.critic import run_critic
from agents.planner import run_planner
from agents.research import run_researcher
from config import Settings, load_prompt
from tools import save_report

settings = Settings()

# ---------------------------------------------------------------------------
# Sub-agent @tool wrappers — exposed to the Supervisor as tools
# ---------------------------------------------------------------------------

@tool
def plan(request: str) -> str:
    """Decompose a research request into a structured plan.

    Sends the request to the Planner Agent, which searches the domain
    and returns a ResearchPlan with goal, search queries, sources, and
    output format. Always call this first before research().
    """
    research_plan = run_planner(request)
    return research_plan.model_dump_json(indent=2)


@tool
def research(request: str, runtime: ToolRuntime) -> str:
    """Execute research using web search and the local knowledge base.

    Sends the instruction to the Research Agent, which follows the plan,
    runs searches, reads pages, and returns Markdown findings.

    IMPORTANT: request MUST be a plain-text string — a natural language
    instruction describing what to research. Do NOT pass JSON objects, dicts,
    or the raw plan output. Convert the plan into a clear text instruction,
    e.g.: "Research X, Y, Z. Focus on A and B. Check the knowledge base first."
    """
    # Count how many times research has already been called in this session.
    messages = runtime.state.get("messages", [])
    research_calls = sum(
        1 for m in messages
        if isinstance(m, ToolMessage) and m.name == "research"
    )
    if research_calls >= settings.max_revisions + 1:
        return (
            f"[REVISION LIMIT REACHED — {research_calls} research rounds completed] "
            f"You have used all {settings.max_revisions} allowed revision rounds. "
            f"You MUST now call save_report() with the best findings gathered. "
            f"Do NOT call research() again."
        )
    return run_researcher(request)


_MAX_FINDINGS_LEN = 6000  # chars — keep critic input within API limits


@tool
def critique(findings: str) -> str:
    """Evaluate research findings and return a structured verdict.

    Sends findings to the Critic Agent, which independently verifies
    freshness, completeness, and structure, then returns a CritiqueResult
    with verdict APPROVE or REVISE, strengths, gaps, and revision_requests.
    Include the original user request in the findings so the Critic can
    assess completeness against it.
    """
    # Strip control characters (null bytes, etc.) that break JSON serialization.
    cleaned = "".join(c for c in findings if c >= " " or c in "\n\t")
    if len(cleaned) > _MAX_FINDINGS_LEN:
        cleaned = cleaned[:_MAX_FINDINGS_LEN] + "\n\n[...truncated for review...]"
    critique_result = run_critic(cleaned)
    return critique_result.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Supervisor Agent
# ---------------------------------------------------------------------------

_model = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

supervisor = create_agent(
    _model,
    tools=[plan, research, critique, save_report],
    system_prompt=load_prompt("supervisor_system", max_revisions=settings.max_revisions),
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={"save_report": True},
            description_prefix="📄 Report requires your approval before saving",
        ),
    ],
    checkpointer=InMemorySaver(),
)

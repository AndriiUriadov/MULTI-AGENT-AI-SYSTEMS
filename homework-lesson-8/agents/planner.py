"""
Planner Agent — decomposes a user request into a structured ResearchPlan.

Exposed:
    planner_agent  — compiled LangGraph agent (create_agent with response_format)
    run_planner(request) → ResearchPlan
"""

from langchain.agents import create_agent
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


def run_planner(request: str) -> ResearchPlan:
    """Invoke the Planner Agent and return a validated ResearchPlan."""
    result = planner_agent.invoke(
        {"messages": [{"role": "user", "content": request}]},
        config={"recursion_limit": settings.max_iterations * 2 + 1},
    )
    return result["structured_response"]

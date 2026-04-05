"""
Planner Agent definition.

build_planner(lc_tools) → compiled LangGraph agent
    response_format=ResearchPlan — returns structured output via result["structured_response"]
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, PLANNER_PROMPT
from schemas import ResearchPlan

settings = Settings()


def build_planner(lc_tools: list):
    """Build and return a Planner agent using the given LangChain tools."""
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.api_key.get_secret_value(),
    )
    return create_agent(
        model,
        tools=lc_tools,
        system_prompt=PLANNER_PROMPT,
        response_format=ResearchPlan,
    )

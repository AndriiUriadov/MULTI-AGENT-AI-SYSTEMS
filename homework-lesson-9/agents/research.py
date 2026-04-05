"""
Research Agent definition.

build_researcher(lc_tools) → compiled LangGraph agent
    Returns plain text findings via result["messages"][-1].content
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, RESEARCHER_PROMPT

settings = Settings()


def build_researcher(lc_tools: list):
    """Build and return a Research agent using the given LangChain tools."""
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.api_key.get_secret_value(),
    )
    return create_agent(
        model,
        tools=lc_tools,
        system_prompt=RESEARCHER_PROMPT,
    )

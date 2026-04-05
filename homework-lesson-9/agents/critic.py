"""
Critic Agent definition.

build_critic(lc_tools) → compiled LangGraph agent
    response_format=CritiqueResult — returns structured output via result["structured_response"]
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, CRITIC_PROMPT
from schemas import CritiqueResult

settings = Settings()


def build_critic(lc_tools: list):
    """Build and return a Critic agent using the given LangChain tools."""
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.api_key.get_secret_value(),
    )
    return create_agent(
        model,
        tools=lc_tools,
        system_prompt=CRITIC_PROMPT,
        response_format=CritiqueResult,
    )

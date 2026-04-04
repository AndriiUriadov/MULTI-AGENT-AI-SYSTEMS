"""
Critic Agent — independently verifies research findings and returns a verdict.

Exposed:
    critic_agent  — compiled LangGraph agent (create_agent with response_format)
    run_critic(findings) → CritiqueResult
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, CRITIC_PROMPT
from schemas import CritiqueResult
from tools import knowledge_search, read_url, web_search

settings = Settings()

_model = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

critic_agent = create_agent(
    _model,
    tools=[web_search, read_url, knowledge_search],
    system_prompt=CRITIC_PROMPT,
    response_format=CritiqueResult,
)


def run_critic(findings: str) -> CritiqueResult:
    """Invoke the Critic Agent and return a validated CritiqueResult."""
    result = critic_agent.invoke(
        {"messages": [{"role": "user", "content": findings}]},
        # Critic makes several verification searches — allow more steps than default.
        config={"recursion_limit": settings.max_iterations * 4 + 1},
    )
    return result["structured_response"]

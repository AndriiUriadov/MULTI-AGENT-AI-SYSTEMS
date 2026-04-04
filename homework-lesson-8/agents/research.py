"""
Research Agent — executes a research plan using web and knowledge base tools.

Exposed:
    researcher_agent  — compiled LangGraph agent
    run_researcher(request) → str  (Markdown findings text)
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import Settings, RESEARCHER_PROMPT
from tools import knowledge_search, read_url, web_search

settings = Settings()

_model = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

researcher_agent = create_agent(
    _model,
    tools=[web_search, read_url, knowledge_search],
    system_prompt=RESEARCHER_PROMPT,
)


def run_researcher(request: str) -> str:
    """Invoke the Research Agent and return findings as a Markdown string."""
    result = researcher_agent.invoke(
        {"messages": [{"role": "user", "content": request}]},
        config={"recursion_limit": settings.max_iterations * 2 + 1},
    )
    return result["messages"][-1].content

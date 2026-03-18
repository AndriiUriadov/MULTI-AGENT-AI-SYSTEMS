from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from config import SYSTEM_PROMPT, Settings
from tools import knowledge_search, read_url, web_search, write_report

settings = Settings()

llm = ChatOpenAI(
    model=settings.model_name,
    api_key=settings.api_key.get_secret_value(),
)

tools = [knowledge_search, web_search, read_url, write_report]

memory = MemorySaver()

_graph = create_react_agent(
    model=llm,
    tools=tools,
    prompt=SYSTEM_PROMPT,
    checkpointer=memory,
)


class _AgentWrapper:
    """Wraps the compiled LangGraph so main.py can call agent.stream(inputs)
    without passing a config dict — MemorySaver requires thread_id, but
    main.py does not pass config. Fixed thread_id is correct for a single-session REPL."""

    def stream(self, inputs):
        config = {
            "configurable": {"thread_id": "session-1"},
            "recursion_limit": 2 * settings.max_iterations + 1,
        }
        yield from _graph.stream(inputs, config)


agent = _AgentWrapper()

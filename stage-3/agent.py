from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from config import SYSTEM_PROMPT, Settings
from tools import read_url, web_search, write_report

settings = Settings()

llm = ChatGoogleGenerativeAI(
    model=settings.model_name,
    google_api_key=settings.api_key.get_secret_value(),
)

tools = [web_search, read_url, write_report]

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
        for chunk in _graph.stream(inputs, config):
            # Gemini returns content as list[dict] instead of str.
            # Normalize it so main.py's `msg.content` check works correctly.
            for node_output in chunk.values():
                for msg in node_output.get("messages", []):
                    if isinstance(msg.content, list):
                        msg.content = " ".join(
                            part.get("text", "") if isinstance(part, dict) else str(part)
                            for part in msg.content
                        ).strip()
            yield chunk


agent = _AgentWrapper()

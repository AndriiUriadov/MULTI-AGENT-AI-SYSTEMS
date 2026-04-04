"""
Крок 0: Верифікація середовища для homework-lesson-8.
Запускати: python verify_env.py
Всі перевірки мають пройти без помилок перед початком реалізації.
"""

import sys
import os

# Заглушка щоб init_chat_model не падав без реального ключа
os.environ.setdefault("OPENAI_API_KEY", "test-key")

errors = []


def check(label: str, fn):
    try:
        fn()
        print(f"  ✓  {label}")
    except Exception as e:
        print(f"  ✗  {label}: {e}")
        errors.append(label)


print(f"Python {sys.version}\n")
print("=== LangChain / LangGraph API ===")

check(
    "langchain.agents.create_agent",
    lambda: __import__("langchain.agents", fromlist=["create_agent"]),
)

check(
    "langchain.agents.middleware.HumanInTheLoopMiddleware",
    lambda: __import__(
        "langchain.agents.middleware", fromlist=["HumanInTheLoopMiddleware"]
    ),
)

check(
    "langchain.chat_models.init_chat_model",
    lambda: __import__("langchain.chat_models", fromlist=["init_chat_model"]),
)

check(
    "langgraph.checkpoint.memory.InMemorySaver",
    lambda: __import__(
        "langgraph.checkpoint.memory", fromlist=["InMemorySaver"]
    ),
)

check(
    "langgraph.types.Command / Interrupt",
    lambda: __import__("langgraph.types", fromlist=["Command", "Interrupt"]),
)

print("\n=== create_agent підтримує response_format (Pydantic) ===")


def _check_response_format():
    from pydantic import BaseModel
    from langchain.agents import create_agent
    from langchain.chat_models import init_chat_model

    class _Plan(BaseModel):
        goal: str
        queries: list[str]

    m = init_chat_model("gpt-4o-mini")
    create_agent(m, tools=[], system_prompt="test", response_format=_Plan)


check("create_agent(response_format=PydanticModel) — ініціалізація", _check_response_format)

print("\n=== RAG залежності ===")

check("faiss-cpu (faiss)", lambda: __import__("faiss"))
check("rank_bm25", lambda: __import__("rank_bm25"))
check("sentence_transformers", lambda: __import__("sentence_transformers"))
check("trafilatura", lambda: __import__("trafilatura"))
check("duckduckgo_search (ddgs)", lambda: __import__("duckduckgo_search"))
check("langchain_openai", lambda: __import__("langchain_openai"))
check("langchain_community", lambda: __import__("langchain_community"))

print("\n=== Версії пакетів ===")
import importlib.metadata as meta

for pkg in ["langchain", "langgraph", "langchain-openai", "langchain-community"]:
    try:
        print(f"  {pkg}: {meta.version(pkg)}")
    except meta.PackageNotFoundError:
        print(f"  {pkg}: НЕ ВСТАНОВЛЕНО")

print()
if errors:
    print(f"FAILED: {len(errors)} перевірок не пройшли: {errors}")
    sys.exit(1)
else:
    print("✅ Всі перевірки пройшли. Середовище готове до реалізації.")

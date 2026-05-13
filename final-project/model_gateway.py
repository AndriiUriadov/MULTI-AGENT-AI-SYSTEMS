"""
Model Gateway — task-aware ChatOpenAI factory with RateLimit fallbacks.

Each agent requests a model by its *task* role, not by model name. The gateway
maps task → primary model (from Settings) and layers LangChain's native
`.with_fallbacks([...])` on top so a RateLimitError/APIError on the primary
model transparently retries on the next one in the chain.

Adding Anthropic or Gemini later: replace `ChatOpenAI(...)` with LangChain's
`init_chat_model(name)` — fallback wiring stays identical.
"""

from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai import APIError, RateLimitError

from config import Settings

Task = Literal["strategist", "writer", "editor", "judge"]

_FALLBACK_EXCEPTIONS = (RateLimitError, APIError)


def _build(model_name: str, api_key: str, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(model=model_name, api_key=api_key, temperature=temperature)


def get_chat_model(task: Task, temperature: float = 0.0) -> BaseChatModel:
    """Return a ChatOpenAI for the task, wrapped with RateLimit fallbacks.

    The primary model comes from `Settings.model_for(task)`; the fallback chain
    from `Settings.fallback_list()` (the primary itself is skipped if it
    appears in the chain to avoid retrying the same model twice).
    """
    settings = Settings()
    api_key = settings.api_key.get_secret_value()
    primary_name = settings.model_for(task)

    fallback_names = [m for m in settings.fallback_list() if m != primary_name]
    if not fallback_names:
        return _build(primary_name, api_key, temperature)

    primary = _build(primary_name, api_key, temperature)
    fallbacks = [_build(name, api_key, temperature) for name in fallback_names]
    return primary.with_fallbacks(fallbacks, exceptions_to_handle=_FALLBACK_EXCEPTIONS)

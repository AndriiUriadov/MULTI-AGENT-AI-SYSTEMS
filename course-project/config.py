"""
Configuration for the course project (Content Creation Pipeline).

Settings       — loaded from .env via pydantic-settings.
load_prompt()  — fetches a versioned system prompt from Langfuse by label.

All agent system prompts live in Langfuse Prompt Management, not in source.
"""

from dotenv import load_dotenv
from langfuse import get_client
from pydantic import SecretStr
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    api_key: SecretStr

    # Model gateway: per-task models + fallback chain.
    model_strategist: str = "gpt-4o-mini"
    model_writer: str = "gpt-4o-mini"
    model_editor: str = "gpt-4o-mini"
    model_judge: str = "gpt-4o-mini"
    fallback_models: str = "gpt-4o-mini,gpt-4o"  # comma-separated

    # Web search
    max_search_results: int = 5
    max_snippet_length: int = 300
    max_url_content_length: int = 5000

    # RAG (shared with hw-8 defaults)
    embedding_model: str = "text-embedding-3-small"
    data_dir: str = "data"
    index_dir: str = "index"
    chunk_size: int = 500
    chunk_overlap: int = 100
    retrieval_top_k: int = 10
    rerank_top_n: int = 3

    # Pipeline
    output_dir: str = "output"
    max_writer_iterations: int = 5  # Evaluator-Optimizer cap (Writer ↔ Editor)

    # Langfuse observability
    langfuse_public_key: SecretStr
    langfuse_secret_key: SecretStr
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_user_id: str = "anonymous"

    # extra=ignore so leftover vars from other projects in .env (e.g. MODEL_NAME
    # from hw-12) don't crash startup.
    model_config = {"env_file": ".env", "extra": "ignore"}

    def fallback_list(self) -> list[str]:
        return [m.strip() for m in self.fallback_models.split(",") if m.strip()]

    def model_for(self, task: str) -> str:
        mapping = {
            "strategist": self.model_strategist,
            "writer": self.model_writer,
            "editor": self.model_editor,
            "judge": self.model_judge,
        }
        if task not in mapping:
            raise ValueError(f"Unknown task: {task!r}. Expected one of {list(mapping)}")
        return mapping[task]


def load_prompt(name: str, **variables: object) -> str:
    """Fetch a production-labelled system prompt from Langfuse."""
    prompt = get_client().get_prompt(name, label="production")
    if variables:
        return prompt.compile(**variables)
    return prompt.prompt

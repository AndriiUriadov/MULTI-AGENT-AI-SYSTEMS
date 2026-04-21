"""
Configuration for homework-lesson-12.

Settings       — loaded from .env via pydantic-settings.
load_prompt()  — fetches a versioned system prompt from Langfuse by label.

All agent system prompts live in Langfuse Prompt Management, not in source.
Change the `production` label in the Langfuse UI → restart Python process →
new prompt takes effect (no code change, no redeploy).
"""

from dotenv import load_dotenv
from langfuse import get_client
from pydantic import SecretStr
from pydantic_settings import BaseSettings

# Load .env into os.environ so the Langfuse SDK can pick up LANGFUSE_* vars
# (pydantic-settings populates the Settings object but does not touch os.environ).
load_dotenv()


class Settings(BaseSettings):
    api_key: SecretStr
    model_name: str = "gpt-4o-mini"

    # Web search
    max_search_results: int = 5
    max_snippet_length: int = 300
    max_url_content_length: int = 5000

    # RAG
    embedding_model: str = "text-embedding-3-small"
    data_dir: str = "data"
    index_dir: str = "index"
    chunk_size: int = 500
    chunk_overlap: int = 100
    retrieval_top_k: int = 10
    rerank_top_n: int = 3

    # Agent loop
    output_dir: str = "output"
    max_iterations: int = 10
    max_revisions: int = 2

    # Langfuse observability
    langfuse_public_key: SecretStr
    langfuse_secret_key: SecretStr
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_user_id: str = "anonymous"

    model_config = {"env_file": ".env"}


def load_prompt(name: str, **variables: object) -> str:
    """Fetch a production-labelled system prompt from Langfuse.

    Template variables use Mustache syntax ({{var}}). Missing prompts raise
    immediately at import time so the process fails loud, not silently.
    """
    prompt = get_client().get_prompt(name, label="production")
    if variables:
        return prompt.compile(**variables)
    return prompt.prompt

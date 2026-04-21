"""
Tools available to the content-pipeline agents.

web_search       — DuckDuckGo (Strategist, Writer, Editor)
read_url         — trafilatura fetch & extract
knowledge_search — brand knowledge base (Strategist only)
save_content     — persist the approved draft as a Markdown file
"""

import os

import trafilatura
from ddgs import DDGS
from langchain.tools import tool

from config import Settings
from retriever import get_retriever

settings = Settings()


@tool
def web_search(query: str) -> list[dict]:
    """Search the web via DuckDuckGo.

    Returns a list of {"title", "url", "snippet"} results. Use to check
    trends, competitors, facts, and statistics.
    """
    try:
        results = DDGS().text(query, max_results=settings.max_search_results)
        return [
            {
                "title": r["title"],
                "url": r["href"],
                "snippet": r["body"][: settings.max_snippet_length],
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


@tool
def read_url(url: str) -> str:
    """Fetch and extract the main text of a webpage (Markdown-safe).

    Returns the article text truncated to avoid filling the context window.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return f"Error: could not fetch content from {url}"
        text = trafilatura.extract(downloaded)
        if not text:
            return f"Error: could not extract readable text from {url}"
        return text[: settings.max_url_content_length]
    except Exception as e:
        return f"Error reading {url}: {str(e)}"


@tool
def knowledge_search(query: str) -> str:
    """Search the brand knowledge base (style guide, brand description, examples).

    Use this at the planning stage to align tone, terminology, and audience
    with the brand. Returns the most relevant excerpts with their source.
    If the brand corpus hasn't been ingested yet, returns a placeholder
    message — the pipeline will still work but without brand grounding.
    """
    try:
        retriever = get_retriever()
        if retriever is None:
            return (
                "(knowledge base not available — "
                "run `python ingest.py` after adding brand docs to data/)"
            )
        docs = retriever.invoke(query)
        if not docs:
            return "No relevant documents found in the brand knowledge base."
        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page")
            location = f"{os.path.basename(source)}"
            if page is not None:
                location += f", page {page}"
            parts.append(f"[{i}] Source: {location}\n{doc.page_content}")
        return "\n\n".join(parts)
    except Exception as e:
        return f"Error searching knowledge base: {str(e)}"


@tool
def save_content(filename: str, content: str) -> str:
    """Save approved Markdown content to the output directory.

    filename: short name without extension (e.g. 'ai-in-healthcare-linkedin').
    content: the final Markdown body.
    Returns the path of the saved file.
    """
    os.makedirs(settings.output_dir, exist_ok=True)
    if not filename.endswith(".md"):
        filename += ".md"
    path = os.path.join(settings.output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Content saved to {path}"

import os

import trafilatura
from ddgs import DDGS
from langchain_core.tools import tool

from config import Settings
from retriever import get_retriever

settings = Settings()


@tool
def web_search(query: str) -> list[dict]:
    """Search the web using DuckDuckGo. Returns a list of results,
    each with 'title', 'url', and 'snippet' fields. Use this to find
    information not covered in the local knowledge base."""
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
    """Fetch and extract the full text content of a webpage at the given URL.
    Returns the main article text, truncated to avoid filling the context window.
    Use this after web_search to get detailed information from a specific page."""
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
def write_report(filename: str, content: str) -> str:
    """Save a Markdown research report to the output directory.
    Returns the full path of the saved file. Always call this at the end
    to persist your research findings."""
    os.makedirs(settings.output_dir, exist_ok=True)
    if not filename.endswith(".md"):
        filename += ".md"
    path = os.path.join(settings.output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Report saved to {path}"


@tool
def knowledge_search(query: str) -> str:
    """Search the local knowledge base using hybrid retrieval and reranking.
    Use this first for questions about topics covered in ingested documents
    (LangChain, LLMs, RAG). Returns the most relevant text excerpts."""
    try:
        retriever = get_retriever()
        docs = retriever.invoke(query)
        if not docs:
            return "No relevant documents found in the knowledge base."
        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "?")
            parts.append(
                f"[{i}] Source: {os.path.basename(source)}, page {page}\n{doc.page_content}"
            )
        return "\n\n".join(parts)
    except Exception as e:
        return f"Error searching knowledge base: {str(e)}"

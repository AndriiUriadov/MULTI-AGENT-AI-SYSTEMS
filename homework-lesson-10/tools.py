"""
Tools available to research agents in homework-lesson-8.

web_search       — DuckDuckGo search (read-only)
read_url         — fetch webpage text (read-only)
knowledge_search — hybrid RAG retrieval from local FAISS index (read-only)
save_report      — write Markdown report to disk (write — HITL-gated in Supervisor)
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
    """Search the web using DuckDuckGo.

    Returns a list of results with 'title', 'url', and 'snippet' fields.
    Use this to find information not covered in the local knowledge base,
    or to check for recent developments.
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
    """Fetch and extract the main text content of a webpage.

    Returns the article text truncated to avoid filling the context window.
    Use this after web_search on the most relevant URLs to get full details.
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
    """Search the local knowledge base using hybrid retrieval and reranking.

    The knowledge base contains ingested PDFs on LangChain, LLMs, and RAG.
    Use this first for any question related to those topics before going to the web.
    Returns the most relevant text excerpts with source document and page number.
    """
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
                f"[{i}] Source: {os.path.basename(source)}, page {page}\n"
                f"{doc.page_content}"
            )
        return "\n\n".join(parts)
    except Exception as e:
        return f"Error searching knowledge base: {str(e)}"


@tool
def save_report(filename: str, content: str) -> str:
    """Save a Markdown research report to the output directory.

    This is a write operation — it requires human approval before executing.
    filename: short name without extension (e.g. 'rag_comparison').
    content: complete Markdown text of the report.
    Returns the full path of the saved file.
    """
    os.makedirs(settings.output_dir, exist_ok=True)
    if not filename.endswith(".md"):
        filename += ".md"
    path = os.path.join(settings.output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Report saved to {path}"

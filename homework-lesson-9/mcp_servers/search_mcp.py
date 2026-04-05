"""
SearchMCP — MCP server exposing search tools to all three agents.

Tools:
    web_search(query)        — DuckDuckGo search
    read_url(url)            — fetch webpage text
    knowledge_search(query)  — hybrid FAISS+BM25+reranker retrieval

Resources:
    resource://knowledge-base-stats — chunk count and index date

Port: 8901 (SEARCH_MCP_PORT from config)
"""

import asyncio
import os
import sys

# Ensure project root is on path so config/retriever resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trafilatura
from ddgs import DDGS
from fastmcp import FastMCP

from config import Settings, SEARCH_MCP_PORT
from retriever import get_retriever

settings = Settings()

mcp = FastMCP(name="SearchMCP")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def web_search(query: str) -> list[dict]:
    """Search the web using DuckDuckGo.

    Returns a list of results with 'title', 'url', and 'snippet' fields.
    Use this to find information not in the local knowledge base or to check
    for recent developments.
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


@mcp.tool()
def read_url(url: str) -> str:
    """Fetch and extract the main text content of a webpage.

    Returns article text truncated to avoid filling the context window.
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


@mcp.tool()
def knowledge_search(query: str) -> str:
    """Search the local knowledge base using hybrid retrieval and reranking.

    The knowledge base contains PDFs on LangChain, LLMs, and RAG.
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


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("resource://knowledge-base-stats")
def knowledge_base_stats() -> str:
    """Statistics about the local knowledge base index."""
    index_dir = settings.index_dir
    chunks_path = os.path.join(index_dir, "chunks.pkl")
    index_path = os.path.join(index_dir, "index.faiss")

    if not os.path.exists(chunks_path):
        return "Knowledge base index not found. Run ingest.py first."

    import pickle
    with open(chunks_path, "rb") as f:
        chunks = pickle.load(f)

    mtime = os.path.getmtime(index_path)
    import datetime
    updated = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

    return (
        f"Knowledge base stats:\n"
        f"  chunks: {len(chunks)}\n"
        f"  index:  {index_path}\n"
        f"  updated: {updated}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(
        mcp.run_async(
            transport="streamable-http",
            host="127.0.0.1",
            port=SEARCH_MCP_PORT,
        )
    )

import os

import trafilatura
from ddgs import DDGS
from langchain_core.tools import tool

from config import Settings

settings = Settings()


@tool
def web_search(query: str) -> list[dict]:
    """Search the web using DuckDuckGo. Returns a list of results,
    each with 'title', 'url', and 'snippet' fields. Use this to discover
    relevant sources before reading full pages with read_url."""
    results = DDGS().text(query, max_results=settings.max_search_results)
    return [
        {"title": r["title"], "url": r["href"], "snippet": r["body"]}
        for r in results
    ]


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

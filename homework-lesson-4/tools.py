import os

import trafilatura
from ddgs import DDGS

from config import Settings

settings = Settings()


# --- Plain Python tool functions ---

def web_search(query: str) -> list[dict]:
    results = DDGS().text(query, max_results=settings.max_search_results)
    return [
        {"title": r["title"], "url": r["href"], "snippet": r["body"]}
        for r in results
    ]


def read_url(url: str) -> str:
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


def write_report(filename: str, content: str) -> str:
    os.makedirs(settings.output_dir, exist_ok=True)
    if not filename.endswith(".md"):
        filename += ".md"
    path = os.path.join(settings.output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Report saved to {path}"


# --- Tool definitions as JSON Schema for Gemini API ---

TOOL_DEFINITIONS = [
    {
        "name": "web_search",
        "description": (
            "Search the web using DuckDuckGo. Returns a list of results, "
            "each with 'title', 'url', and 'snippet' fields. "
            "Use this first to discover relevant sources."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_url",
        "description": (
            "Fetch and extract the full text content of a webpage at the given URL. "
            "Returns the main article text, truncated to avoid filling the context window. "
            "Use this after web_search to get detailed information from a specific page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the webpage to read.",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "write_report",
        "description": (
            "Save a Markdown research report to the output directory. "
            "Returns the full path of the saved file. "
            "Always call this as the final step to persist your research findings."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name for the report file (without .md extension).",
                },
                "content": {
                    "type": "string",
                    "description": "Full Markdown content of the report.",
                },
            },
            "required": ["filename", "content"],
        },
    },
]


_TOOL_MAP = {
    "web_search": web_search,
    "read_url": read_url,
    "write_report": write_report,
}


def execute_tool(name: str, args: dict) -> str:
    fn = _TOOL_MAP.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'"
    result = fn(**args)
    # Serialize to string so it can be sent back to the model
    return str(result)

"""
ReportMCP — MCP server exposing the save_report tool.

Tools:
    save_report(filename, content) — write Markdown report to output/

Resources:
    resource://output-dir — path and list of saved reports

Port: 8902 (REPORT_MCP_PORT from config)
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP

from config import Settings, REPORT_MCP_PORT

settings = Settings()

mcp = FastMCP(name="ReportMCP")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def save_report(filename: str, content: str) -> str:
    """Save a Markdown research report to the output directory.

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


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("resource://output-dir")
def output_dir_info() -> str:
    """Information about the output directory and saved reports."""
    out = settings.output_dir
    if not os.path.exists(out):
        return f"Output directory '{out}' does not exist yet. No reports saved."

    files = [f for f in os.listdir(out) if f.endswith(".md")]
    files.sort()

    lines = [f"Output directory: {os.path.abspath(out)}", f"Saved reports ({len(files)}):"]
    for f in files:
        path = os.path.join(out, f)
        size = os.path.getsize(path)
        lines.append(f"  - {f}  ({size} bytes)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(
        mcp.run_async(
            transport="streamable-http",
            host="127.0.0.1",
            port=REPORT_MCP_PORT,
        )
    )

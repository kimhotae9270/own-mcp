# tools/core.py
from __future__ import annotations

from fastmcp import FastMCP
from typing import Dict, List
import time


def register_core_tools(mcp: FastMCP) -> None:

    @mcp.tool
    def server_info() -> Dict[str, str]:
        """Returns basic server metadata."""
        return {
            "name": "KB-Ingest-Summarizer",
            "capabilities": "summarize_youtube (now), summarize_blog (todo), summarize_paper (todo)",
        }

    @mcp.tool
    def now_unix() -> Dict[str, int]:
        """Returns current unix timestamp."""
        return {"unix": int(time.time())}

    @mcp.tool
    def supported_sources() -> Dict[str, List[str]]:
        """Lists supported input source types."""
        return {
            "sources": ["youtube"],
            "planned": ["blog/article", "paper/arxiv/pdf"],
        }

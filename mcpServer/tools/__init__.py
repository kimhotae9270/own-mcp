# tools/__init__.py
from fastmcp import FastMCP

from .summary_tools.core import register_core_tools
from .summary_tools.youtube import register_youtube_tools
from .summary_tools.paper import register_paper_tools


def register_all_tools(mcp: FastMCP) -> None:
    #register_core_tools(mcp)
    register_youtube_tools(mcp)

    register_paper_tools(mcp)

# tools/__init__.py
from fastmcp import FastMCP

from .core import register_core_tools
from .youtube import register_youtube_tools
from .blog import register_blog_tools
from .paper import register_paper_tools


def register_all_tools(mcp: FastMCP) -> None:
    register_core_tools(mcp)
    register_youtube_tools(mcp)
    register_blog_tools(mcp)
    register_paper_tools(mcp)

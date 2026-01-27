# tools/blog.py
from fastmcp import FastMCP
from typing import Dict

def register_blog_tools(mcp: FastMCP) -> None:
    @mcp.tool
    def blog_summarize(url: str) -> Dict[str, str]:
        """TODO: Extract main content (readability) and summarize."""
        return {"ok": "false", "message": "TODO: blog_summarize not implemented yet."}

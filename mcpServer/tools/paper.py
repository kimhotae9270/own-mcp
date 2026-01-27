# tools/paper.py
from fastmcp import FastMCP
from typing import Dict

def register_paper_tools(mcp: FastMCP) -> None:
    @mcp.tool
    def paper_summarize(url: str) -> Dict[str, str]:
        """TODO: Handle arXiv/DOI/PDF fetch + section extraction + summarize."""
        return {"ok": "false", "message": "TODO: paper_summarize not implemented yet."}

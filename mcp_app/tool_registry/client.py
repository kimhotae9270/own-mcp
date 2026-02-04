from fastmcp import Client as MCPClient
import os

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000")

_mcp_client = None

def get_mcp_client():
    global _mcp_client

    if _mcp_client is None:
        _mcp_client = MCPClient(MCP_URL)

    return _mcp_client

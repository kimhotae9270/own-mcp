from .client import get_mcp_client

_tool_cache = None

async def get_all_tools():
    global _tool_cache

    if _tool_cache is not None:
        return _tool_cache

    mcp = get_mcp_client()

    async with mcp:
        _tool_cache = await mcp.list_tools()

    return _tool_cache

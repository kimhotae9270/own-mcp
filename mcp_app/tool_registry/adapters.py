from typing import Any, Dict, List

def mcp_tools_to_openai_tools(mcp_tools) -> List[Dict[str, Any]]:
    """
    fastmcp list_tools() → OpenAI tools schema 변환
    """
    tools = []
    for t in mcp_tools:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": getattr(t, "inputSchema", {"type": "object"}),
                },
            }
        )
    return tools
import os
import json
from typing import List, Dict, Any

from openai import AsyncOpenAI
from fastmcp import Client as MCPClient

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000")

oai = AsyncOpenAI()


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


async def run_mcp_agent(user_text: str) -> str:
    """
    LLM → tool_calls → MCP → LLM 재호출
    """
    mcp = MCPClient(MCP_URL)

    async with mcp:
        # 1) MCP tools
        mcp_tools = await mcp.list_tools()
        openai_tools = mcp_tools_to_openai_tools(mcp_tools)

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a tool-using assistant.\n"
                    "If a tool can produce an exact result, use it.\n"
                    "After using tools, answer concisely."
                ),
            },
            {"role": "user", "content": user_text},
        ]

        # 2) 1차 호출 (tool 판단)
        resp = await oai.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
        )

        msg = resp.choices[0].message

        # tool 안 쓰면 바로 종료
        if not msg.tool_calls:
            return msg.content or ""

        # 3) assistant(tool_calls) 메시지 추가
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    tc.model_dump() if hasattr(tc, "model_dump") else {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # 4) MCP 실행
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = await mcp.call_tool(tc.function.name, args)

            # CallToolResult는 JSON 직렬화 안 되므로 str()로 안전 처리
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                }
            )

        # 5) 재호출 → 최종 답변
        resp2 = await oai.chat.completions.create(
            model=MODEL,
            messages=messages,
        )

        return resp2.choices[0].message.content or ""

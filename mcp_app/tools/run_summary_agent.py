import os
import json
from typing import List, Dict, Any

from openai import AsyncOpenAI
from fastmcp import Client as MCPClient

from typing import Any, Dict, List
import json
from mcp_app.tool_registry.adapters import mcp_tools_to_openai_tools
from mcp_app.llm.client import get_llm

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000")

def has_tag(tool, target_tag: str) -> bool:
    desc = (tool.description or "").lower()

    for line in desc.split("\n"):
        if line.strip().startswith("tags:"):
            tags = [t.strip() for t in line.replace("Tags:", "").replace("tags:", "").split(",")]
            return target_tag.lower() in tags

    return False


async def run_summary_agent(user_text: str) -> str:
    """
    LLM → tool_calls → MCP → LLM 재호출
    """
    llm = get_llm()
    mcp = MCPClient(MCP_URL)

    async with mcp:
        # 1) MCP tools
        mcp_tools = await mcp.list_tools()

        summary_tools = [
            t for t in mcp_tools
            if has_tag(t, "summary")
        ]

        openai_tools = mcp_tools_to_openai_tools(summary_tools)

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a tool-using assistant.\n"
                    "You are a summarization assistant. Use the provided tools whenever possible.\n"
                    "After using tools, answer concisely."
                ),
            },
            {"role": "user", "content": user_text},
        ]

        # 2) 1차 호출 (tool 판단)
        resp = await llm.chat.completions.create(
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

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                }
            )

        # 5) 재호출 → 최종 답변
        resp2 = await llm.chat.completions.create(
            model=MODEL,
            messages=messages,
        )

        return resp2.choices[0].message.content or ""


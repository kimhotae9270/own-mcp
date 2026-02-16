# tools/agents/run_calendar_agent.py

import os
import json
from typing import List, Dict, Any

from agent.llm.client import get_llm
from agent.tool_registry.registry import get_tools_by_tags, call_tool
from agent.tool_registry.adapters import tools_to_openai_tools

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# 툴 등록을 위해 import
import agent.tools.impl.calendar_tools# noqa


async def run_calendar_agent(user_text: str, *, ctx: dict) -> str:
    """
    Calendar agent orchestration loop.
    ctx must contain user_id.
    """

    if "user_id" not in ctx:
        raise ValueError("ctx must include user_id")

    llm = get_llm()

    calendar_tools = get_tools_by_tags(["calendar"])
    openai_tools = tools_to_openai_tools(calendar_tools)

    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a calendar assistant.\n"
                "Use calendar tools when needed.\n"
                "Ask clarifying questions if required time info is missing.\n"
                "Return concise responses."
            ),
        },
        {"role": "user", "content": user_text},
    ]

    resp = await llm.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=openai_tools,
        tool_choice="auto",
    )

    msg = resp.choices[0].message

    if not msg.tool_calls:
        return msg.content or ""

    messages.append(
        {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
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

    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments or "{}")
        result = await call_tool(tc.function.name, args, ctx)

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    resp2 = await llm.chat.completions.create(
        model=MODEL,
        messages=messages,
    )

    return resp2.choices[0].message.content or ""

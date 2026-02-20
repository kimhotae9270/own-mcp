# tools/agents/run_calendar_agent.py

import os
import json
from typing import List, Dict, Any

from agent.llm.client import get_llm
from agent.tool_registry.registry import get_tools_by_tags, call_tool
from agent.tool_registry.adapters import tools_to_openai_tools
from datetime import datetime, timezone, timedelta

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# 툴 등록을 위해 import
import agent.tools.impl.calendar_tools# noqa


async def run_calendar_agent(user_text: str, *, ctx: dict) -> str:
    """
    Calendar agent orchestration loop.
    ctx must contain user_id.
    """
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    today_str = now.strftime("%Y-%m-%d")
    current_year = now.year

    if "user_id" not in ctx:
        raise ValueError("ctx must include user_id")

    llm = get_llm()

    calendar_tools = get_tools_by_tags(["calendar"])
    openai_tools = tools_to_openai_tools(calendar_tools)

    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": f"""
                You are a calendar assistant that helps the user manage Google Calendar.
                
                Context:
                - Today's date is {today_str} in Asia/Seoul (KST, UTC+09:00).
                - The current year is {current_year}.
                
                Core rules (VERY IMPORTANT):
                1) Date interpretation
                - If the user specifies month/day but does NOT specify a year, assume year = {current_year}.
                - Interpret relative terms like "today", "tomorrow", "this weekend", "next week" relative to today's date above.
                - If the user's request is ambiguous (missing year, missing month/day, missing time when time is required), ask a clarifying question instead of guessing.
                
                2) Prevent accidental past events
                - Do NOT create events in the past unless the user explicitly requests a past date/year.
                - If the date you inferred would be in the past and the user did not explicitly ask for the past, ask a clarification question.
                
                3) All-day vs timed events
                - If the user does NOT specify a time (e.g., they only say a date like "2월 28일" / "Feb 28"), create an ALL-DAY event.
                  - Use all_day=true.
                  - Use start/end as dates in 'YYYY-MM-DD' format.
                  - IMPORTANT: For all-day events, end date must be the NEXT day (exclusive end).
                    Example: start=2026-02-28, end=2026-03-01.
                - If the user specifies a time or a time range, create a TIMED event.
                  - Use all_day=false (or omit it if the tool default is false).
                  - Use ISO 8601 dateTime with timezone offset (+09:00), e.g. '2026-02-28T10:00:00+09:00'.
                
                4) Tool usage
                - Use calendar tools to create/list/delete events when needed.
                - If you need to confirm the result (debugging or user asks), list events around the target time window after creating.
                - Keep responses concise and user-friendly.
                
                Output style:
                - If you need clarification, ask 1-2 short questions.
                - Otherwise, confirm what you did (title + date/time) in Korean.
                """.strip(),
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

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from agent.llm.client import get_llm

from agent.graph.actions import Action, ReactSession, FinalAction, HandoffAction
from agent.tool_registry.registry import list_tools_filtered, call_tool
from agent.tool_registry.adapters import tools_to_openai_tools
import agent.tools.impl.notice_tools
from agent.tools.agents._tool_loop import (
    inject_conversation_memory,
    run_openai_tool_loop,
)


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _mk_system_prompt() -> str:
    return (
        "You are a tool-using agent.\n"
        "Use the provided tools when needed.\n"
        "Never fabricate tool results.\n"
        "\n"
        "IMPORTANT:\n"
        "- Call AT MOST ONE tool per step.\n"
        "- If the request is about calendars, schedules, events, adding, deleting, listing, or modifying events,\n"
        "  you MUST call the tool `handoff_calendar_agent`.\n"
        "- For calendar-related requests, DO NOT answer directly in natural language without calling the tool.\n"
        "- Only provide a natural language answer after the tool has been executed.\n"
    )


async def run_react_agent(
    text: str,
    ctx: Dict[str, Any],
    max_steps: int = 6,
    *,
    resume_messages: Optional[List[Dict[str, Any]]] = None,
    resume_seen_calls: Optional[List[str]] = None,
    resume_steps_used: int = 0,
) -> Action:
    llm = get_llm()

    # 세션 재개인데 이미 스텝을 다 썼다면 바로 종료 (기존 동작 유지)
    if int(max_steps) - int(resume_steps_used) <= 0:
        return FinalAction(
            type="final",
            answer="최대 스텝을 초과했어.",
            trace=[],
        )

    extra_exclude_names = ctx.get("exclude_tool_names") or []
    extra_exclude_tags = ctx.get("exclude_tool_tags") or []

    tool_defs = list_tools_filtered(
        exclude_names=extra_exclude_names,
        exclude_tags=extra_exclude_tags,
    )
    tool_names = [t.name for t in tool_defs]
    tools_spec = tools_to_openai_tools(tool_defs)
    if resume_messages is not None:
        messages: List[Dict[str, Any]] = resume_messages
    else:
        messages = [{"role": "system", "content": _mk_system_prompt()}]
        messages = inject_conversation_memory(messages, ctx, max_turns=2)
        messages.append({"role": "user", "content": text})

    result = await run_openai_tool_loop(
        llm=llm,
        model=MODEL,
        messages=messages,
        tools_spec=tools_spec,
        ctx=ctx,
        call_tool_fn=call_tool,
        max_steps=max_steps,
        start_step=int(resume_steps_used),
        seen_calls=set(resume_seen_calls or []),
        allow_multiple_tool_calls=False,
        tool_names_allowlist=set(tool_names),
        duplicate_policy="stop",
        arguments_mode="json",  # run_react_agent 기존과 동일하게 JSON 문자열로 저장
        tool_result_serializer=lambda obs: str(obs),
        handoff_tools={"handoff_calendar_agent"},
        unknown_tool_final_message=lambda name: f"{name} 도구는 사용할 수 없어.",
        duplicate_final_message="같은 도구 호출이 반복되어 중단했어.",
        max_steps_final_message="도구 호출이 길어져서 중단했어.",
        trace_prefix="react",
    )

    trace = result.get("trace") or []

    if result["type"] == "handoff":
        tc = result["tool_call"]
        call_id = tc["id"]
        name = tc["name"]
        args = tc.get("arguments") or {}

        react_session: ReactSession = {
            "messages": result["messages"],
            "seen_calls": result["seen_calls"],
            "steps_used": int(result["steps_used"]),
            "max_steps": int(max_steps),
            "pending_tool_call": {"id": call_id, "name": name, "arguments": args},
        }

        return HandoffAction(
            type="handoff",
            route="CALENDAR",
            payload={
                "user_text": args.get("user_text", text),
                "react_session": react_session,
                "tool_call_id": call_id,
                "tool_name": name,
            },
            trace=trace,
        )

    react_session: ReactSession = {
        "messages": result["messages"],
        "seen_calls": result["seen_calls"],
        "steps_used": int(result["steps_used"]),
        "max_steps": int(max_steps),
    }

    return FinalAction(
        type="final",
        answer=result["content"],
        trace=trace,
        used_tools=bool(result.get("used_tools")),
        react_session=react_session,
    )
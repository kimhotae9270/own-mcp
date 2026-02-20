# agent/tools/agents/run_react_agent.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import json

from agent.llm.client import get_llm
from agent.tool_registry.registry import list_tools_filtered

CALENDAR_ROUTE_SENTINEL = "__ROUTE__:CALENDAR"


def _is_calendar_tool_name(name: str) -> bool:
    n = (name or "").lower()
    return ("calendar" in n) or ("gcal" in n) or ("캘린더" in n) or ("일정" in n)


def _pack_calendar_handoff(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    user_text: str,
    react_session: Dict[str, Any],
) -> str:
    payload = {
        "tool_name": tool_name,
        "tool_args": tool_args,
        "user_text": user_text,
        # ReAct를 캘린더 노드 이후 "이어" 돌리기 위한 세션 스냅샷
        "react_session": react_session,
    }
    return CALENDAR_ROUTE_SENTINEL + "::" + json.dumps(payload, ensure_ascii=False)


def _mk_system_prompt() -> str:
    return (
        "You are a tool-using agent.\n"
        "Use the provided tools when helpful.\n"
        "If you can answer without tools, answer directly.\n"
        "Never fabricate tool results.\n"
        "\n"
        "IMPORTANT:\n"
        "- Call AT MOST ONE tool per step.\n"
        "- Calendar tools may appear in the tool list for planning, but MUST NOT be executed here.\n"
        "- If a calendar tool is selected, return a CALENDAR route handoff instead.\n"
    )


def _get_tool_names_from_registry(ctx: Dict[str, Any]) -> List[str]:
    extra_exclude_names = ctx.get("exclude_tool_names") or []
    extra_exclude_tags = ctx.get("exclude_tool_tags") or []
    defs = list_tools_filtered(exclude_names=extra_exclude_names, exclude_tags=extra_exclude_tags)
    return [t.name for t in defs]


async def run_react_agent(
    text: str,
    ctx: Dict[str, Any],
    max_steps: int = 6,
    *,
    # resume 지원 (캘린더 노드 후 ReAct 재개)
    resume_messages: Optional[List[Dict[str, Any]]] = None,
    resume_seen_calls: Optional[List[str]] = None,
    resume_steps_used: int = 0,
) -> Tuple[str, List[str]]:
    trace: List[str] = []
    llm = get_llm()

    toolkit = ctx.get("toolkit")
    if toolkit is None:
        trace.append("react: no toolkit in ctx -> answered without tools")
        return (
            "(도구 실행 환경(toolkit)이 아직 연결되지 않았어. 일단 질문에 대해 설명만 할게.)\n\n" + text,
            trace,
        )

    tool_names = _get_tool_names_from_registry(ctx)
    tools_spec = toolkit.get_tools(tool_names)

    # 새 세션 vs 재개 세션
    messages: List[Dict[str, Any]] = (
        resume_messages
        if resume_messages is not None
        else [
            {"role": "system", "content": _mk_system_prompt()},
            {"role": "user", "content": text},
        ]
    )

    # 루프 방지 (tool name + args signature)
    seen_calls = set(resume_seen_calls or [])

    steps_left = max(0, max_steps - int(resume_steps_used))
    if steps_left == 0:
        return ("(이전 단계에서 이미 최대 스텝을 사용했어) 요청을 더 구체적으로 줄래?", trace)

    for step_offset in range(1, steps_left + 1):
        step = resume_steps_used + step_offset
        trace.append(f"react: step {step}/{max_steps}")

        resp = await llm.responses.create(
            model="gpt-4o-mini",
            input=messages,
            tools=tools_spec,
        )

        tool_calls = toolkit.extract_tool_calls(resp)

        if not tool_calls:
            trace.append("react: finished (no tool calls)")
            return resp.output_text.strip(), trace

        call = tool_calls[0]  # one tool per step
        name = call["name"]
        args = call.get("arguments") or {}

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"_raw": args}

        # 후보 밖 툴이면 막기 (단, 캘린더 계열이면 handoff)
        if name not in tool_names:
            trace.append(f"react: tool not available in this node -> {name}")
            if _is_calendar_tool_name(name):
                trace.append("react: calendar tool call attempted -> escape to CALENDAR route")
                react_session = {
                    "messages": messages,
                    "seen_calls": list(seen_calls),
                    "steps_used": step - 1,  # 이 단계(tool 실행 전)까지 사용한 스텝
                    "max_steps": max_steps,
                }
                return (
                    _pack_calendar_handoff(
                        tool_name=name,
                        tool_args=args,
                        user_text=text,
                        react_session=react_session,
                    ),
                    trace,
                )

            return (
                f"'{name}' 도구는 현재 노드에서 사용할 수 없어. "
                "요청이 캘린더 작업 중심이면 캘린더 경로로 다시 요청해줘.",
                trace,
            )

        # ✅ A안: 캘린더 툴이면 '선택'까지만 하고 실행은 캘린더 노드로 넘김
        if _is_calendar_tool_name(name):
            trace.append(f"react: calendar tool selected -> handoff to CALENDAR ({name})")
            react_session = {
                "messages": messages,
                "seen_calls": list(seen_calls),
                "steps_used": step - 1,
                "max_steps": max_steps,
            }
            return (
                _pack_calendar_handoff(
                    tool_name=name,
                    tool_args=args,
                    user_text=text,
                    react_session=react_session,
                ),
                trace,
            )

        sig = name + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)
        if sig in seen_calls:
            trace.append(f"react: loop detected -> {name} args repeat, stop")
            return (
                "같은 도구 호출이 반복되어 루프를 중단했어. "
                "요청을 더 구체적으로(대상/기간/키워드) 말해줘.",
                trace,
            )
        seen_calls.add(sig)

        observation = await toolkit.call_tool(name, args)
        trace.append(f"react: tool -> {name} ok")

        # tool 결과를 다음 reasoning에 주입
        messages.append({"role": "tool", "name": name, "content": str(observation)})

    trace.append("react: hit max_steps, stopped")
    return ("도구 호출이 길어져서 중단했어. 범위를 더 좁혀서 다시 요청해줘.", trace)
# agent/tools/agents/run_react_agent.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import json

from agent.llm.client import get_llm
from agent.tool_registry.registry import list_tools_filtered  # ✅ 정책 기반 필터 적용

CALENDAR_ROUTE_SENTINEL = "__ROUTE__:CALENDAR"


def _is_calendar_tool_name(name: str) -> bool:
    n = (name or "").lower()
    # tool naming conventions: google calendar, gcal, calendar, 일정/캘린더
    return ("calendar" in n) or ("gcal" in n) or ("캘린더" in n) or ("일정" in n)

def _pack_calendar_handoff(*, tool_name: str, tool_args: Dict[str, Any], user_text: str) -> str:
    payload = {
        "tool_name": tool_name,
        "tool_args": tool_args,
        "user_text": user_text,
    }
    return CALENDAR_ROUTE_SENTINEL + "::" + json.dumps(payload, ensure_ascii=False)

def _mk_system_prompt() -> str:
    return (
        "You are a tool-using agent.\n"
        "Use the provided tools when helpful.\n"
        "If you can answer without tools, answer directly.\n"
        "If you are not sure which tool to use, ask a brief follow-up question.\n"
        "Never fabricate tool results.\n"
        "IMPORTANT: Calendar tools may appear in the tool list for planning, but MUST NOT be executed here.\n"
        "If a calendar tool is selected, return a CALENDAR route handoff instead.\n"
    )



def _get_tool_names_from_registry(ctx: Dict[str, Any]) -> List[str]:
    """ReAct 노드에서 노출할 툴 이름 목록을 레지스트리 정책으로부터 생성.
    - 기본: policy.py의 REACT_EXCLUDE_TAGS/TOOLS 적용(list_tools_filtered)
    - 추가로 ctx에서 exclude_tool_names / exclude_tool_tags를 넘기면 더 제외 가능
    """
    extra_exclude_names = ctx.get("exclude_tool_names") or []
    extra_exclude_tags = ctx.get("exclude_tool_tags") or []
    defs = list_tools_filtered(exclude_names=extra_exclude_names, exclude_tags=extra_exclude_tags)
    return [t.name for t in defs]

async def run_react_agent(
    text: str,
    ctx: Dict[str, Any],
    max_steps: int = 6,
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

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _mk_system_prompt()},
        {"role": "user", "content": text},
    ]

    seen_calls = set()

    for step in range(1, max_steps + 1):
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

        for call in tool_calls:
            name = call["name"]
            args = call.get("arguments") or {}

            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"_raw": args}

            # 후보 밖(tool_names에 없는) 툴 호출 시:
            # - 특히 캘린더 계열 툴이면 CALENDAR 노드로 탈출
            if name not in tool_names:
                trace.append(f"react: tool not available in this node -> {name}")
                if _is_calendar_tool_name(name):
                    trace.append("react: calendar tool call attempted -> escape to CALENDAR route")
                    return (_pack_calendar_handoff(tool_name=name, tool_args=args, user_text=text), trace)
                return (
                    f"'{name}' 도구는 현재 노드에서 사용할 수 없어. "
                    "요청이 캘린더 작업 중심이면 캘린더 경로로 다시 요청해줘.",
                    trace,
                )

            # A안: 캘린더 툴은 ReAct에서 "선택"까지만 하고 실행은 CALENDAR 노드로 넘긴다.
            if _is_calendar_tool_name(name):
                trace.append(f"react: calendar tool selected -> handoff to CALENDAR ({name})")
                return (_pack_calendar_handoff(tool_name=name, tool_args=args, user_text=text), trace)

            sig = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if sig in seen_calls:
                trace.append(f"react: loop detected -> {name} args repeat, stop")
                return (
                    "같은 도구 호출이 반복되어 루프를 중단했어. "
                    "요청을 조금 더 구체적으로 말해주거나(대상/기간/키워드), "
                    "원하는 결과 형태를 알려줘.",
                    trace,
                )
            seen_calls.add(sig)

            observation = await toolkit.call_tool(name, args)
            trace.append(f"react: tool -> {name} ok")

            messages.append({"role": "tool", "name": name, "content": str(observation)})

    trace.append("react: hit max_steps, stopped")
    return (
        "도구 호출이 길어져서 중단했어. 범위를 더 좁혀서 다시 요청해줘.",
        trace,
    )
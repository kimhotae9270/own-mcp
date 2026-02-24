"""agent/tools/agents/_tool_loop.py

Shared utilities + an OpenAI tool-calling loop used by:
- run_react_agent
- run_calendar_agent

Why this exists
- Both agents implement the same 'tool-call -> tool-result -> model -> ...' pattern.
- Keeping one implementation reduces drift and fixes bugs in one place.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Set, TypedDict


Message = Dict[str, Any]


class ParsedToolCall(TypedDict):
    id: str
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str


class ToolLoopFinal(TypedDict):
    type: Literal["final"]
    content: str
    messages: List[Message]
    seen_calls: List[str]
    steps_used: int
    used_tools: bool
    trace: List[str]


class ToolLoopHandoff(TypedDict):
    type: Literal["handoff"]
    tool_call: ParsedToolCall
    messages: List[Message]
    seen_calls: List[str]
    steps_used: int
    used_tools: bool
    trace: List[str]


ToolLoopResult = ToolLoopFinal | ToolLoopHandoff


CallToolFn = Callable[[str, Dict[str, Any], Dict[str, Any]], Awaitable[Any]]


def inject_conversation_memory(
    messages: List[Message],
    ctx: Dict[str, Any],
    *,
    max_turns: int = 2,
) -> List[Message]:
    """Injects conversation summary + recent turns (user/assistant only).

    - summary -> system message
    - recent -> last N turns (2 * max_turns messages)
    """
    mem = (ctx or {}).get("memory") or {}
    recent = mem.get("recent") or []
    summary = (mem.get("summary") or "").strip()

    keep_n = max(0, 2 * int(max_turns))
    recent_slice = recent[-keep_n:] if keep_n else []

    if summary:
        messages.append({
            "role": "system",
            "content": f"Conversation summary (for context):\n{summary}",
        })

    for m in recent_slice:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})

    return messages


def safe_json_loads(s: Any) -> Dict[str, Any]:
    """Best-effort JSON parser for tool-call arguments.

    - If s is already a dict -> returns it
    - If s is a string JSON -> returns parsed dict
    - Otherwise -> returns {'_raw': <original>}
    """
    if s is None:
        return {}
    if isinstance(s, dict):
        return s
    if not isinstance(s, str):
        return {"_raw": s}

    try:
        if not s:
            return {}
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else {"_raw": parsed}
    except Exception:
        return {"_raw": s}


def make_tool_call_sig(tool_name: str, args: Dict[str, Any]) -> str:
    return tool_name + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)


def extract_tool_calls(openai_message: Any) -> List[ParsedToolCall]:
    """Extract tool-calls from an OpenAI message object.

    Supports both:
    - OpenAI SDK objects (tc.id, tc.function.name, tc.function.arguments)
    - dict-like payloads (for tests/mocks)
    """
    tool_calls = getattr(openai_message, "tool_calls", None) or []
    out: List[ParsedToolCall] = []

    for tc in tool_calls:
        # tool call id
        call_id = getattr(tc, "id", None)
        if call_id is None and isinstance(tc, dict):
            call_id = tc.get("id")

        fn = getattr(tc, "function", None)
        if fn is None and isinstance(tc, dict):
            fn = tc.get("function")

        name = getattr(fn, "name", None) if fn is not None else None
        raw_args = getattr(fn, "arguments", None) if fn is not None else None

        if isinstance(fn, dict):
            name = fn.get("name")
            raw_args = fn.get("arguments")

        if not call_id or not name:
            # Skip malformed tool calls
            continue

        # OpenAI expects tool-call arguments to be a string.
        raw_args_str = raw_args if isinstance(raw_args, str) else json.dumps(raw_args or {}, ensure_ascii=False)
        args = safe_json_loads(raw_args_str)

        out.append({
            "id": str(call_id),
            "name": str(name),
            "arguments": args,
            "raw_arguments": raw_args_str,
        })

    return out


def append_assistant_tool_calls(
    messages: List[Message],
    *,
    content: Optional[str],
    tool_calls: List[ParsedToolCall],
    arguments_mode: Literal["raw", "json"] = "raw",
) -> None:
    """Append an assistant message that contains tool_calls.

    arguments_mode:
    - raw: keep original arguments string from the model
    - json: dump parsed dict to JSON string (stable-ish)
    """
    tc_payload: List[Dict[str, Any]] = []
    for tc in tool_calls:
        if arguments_mode == "json":
            args_str = json.dumps(tc.get("arguments") or {}, ensure_ascii=False)
        else:
            args_str = tc.get("raw_arguments") or "{}"

        tc_payload.append({
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": args_str,
            },
        })

    messages.append({
        "role": "assistant",
        "content": content,
        "tool_calls": tc_payload,
    })


def append_tool_result(
    messages: List[Message],
    *,
    tool_call_id: str,
    content: str,
) -> None:
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    })

def store_tool_observation(
    ctx: Dict[str, Any],
    *,
    tool_call_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    observation: Any,
) -> None:
    """
    Store full tool observations in ctx so downstream nodes (e.g., chat_node) can use them.

    We intentionally keep the *tool message content* sent back to the LLM small to reduce latency and
    to prevent the ReAct node from seeing large payloads. The full payload lives in ctx['_tool_store'].
    """
    if not isinstance(ctx, dict):
        return

    store = ctx.setdefault("_tool_store", {})
    if not isinstance(store, dict):
        store = {}
        ctx["_tool_store"] = store

    store[str(tool_call_id)] = {
        "tool": str(tool_name),
        "arguments": arguments,
        "result": observation,   # ✅ FULL 결과 저장
    }


def minimal_tool_ack(tool_call_id: str) -> str:
    """Small tool result payload returned to the model."""
    return json.dumps({"ok": True, "stored": True, "key": str(tool_call_id)}, ensure_ascii=False)


async def run_openai_tool_loop(
    *,
    llm: Any,
    model: str,
    messages: List[Message],
    tools_spec: List[Dict[str, Any]],
    ctx: Dict[str, Any],
    call_tool_fn: CallToolFn,
    max_steps: int,
    start_step: int = 0,
    seen_calls: Optional[Set[str]] = None,
    allow_multiple_tool_calls: bool = True,
    tool_names_allowlist: Optional[Set[str]] = None,
    duplicate_policy: Literal["stop", "tool_error"] = "stop",
    arguments_mode: Literal["raw", "json"] = "raw",
    tool_result_serializer: Callable[[Any], str] = lambda x: str(x),
    handoff_tools: Optional[Set[str]] = None,
    unknown_tool_final_message: Callable[[str], str] = lambda name: f"{name} 도구는 사용할 수 없어.",
    duplicate_final_message: str = "같은 도구 호출이 반복되어 중단했어.",
    max_steps_final_message: str = "도구 호출이 길어져서 중단했어.",
    trace_prefix: str = "tool",
) -> ToolLoopResult:
    """Generic OpenAI tool-calling loop.

    Returns:
    - {type='final', content=...}
    - {type='handoff', tool_call=...}
    """

    trace: List[str] = []
    seen: Set[str] = set(seen_calls or set())

    # If messages already include a tool result, we consider tools as "used".
    used_tools = any(
        isinstance(m, dict) and m.get("role") == "tool" for m in (messages or [])
    )

    steps_left = max(0, int(max_steps) - int(start_step))
    if steps_left == 0:
        return {
            "type": "final",
            "content": max_steps_final_message,
            "messages": messages,
            "seen_calls": list(seen),
            "steps_used": int(start_step),
            "used_tools": used_tools,
            "trace": trace,
        }
    import time
    for step_offset in range(1, steps_left + 1):
        step = int(start_step) + step_offset
        trace.append(f"{trace_prefix}: step {step}/{max_steps}")
        print("=== LLM INPUT MESSAGES ===")
        for m in messages:
            print(m)
        print("===========================")
        t0 = time.perf_counter()
        resp = await llm.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_spec,
            tool_choice="auto",
        )
        t1 = time.perf_counter()
        print(f"{trace_prefix}: llm_ms={(t1 - t0) * 1000:.1f}")
        msg = resp.choices[0].message
        print("=== LLM OUTPUT MESSAGES ===")
        print(msg)
        print("===========================")
        calls = extract_tool_calls(msg)
        if not calls:
            trace.append(f"{trace_prefix}: finished")
            if getattr(msg, "content", None):
                messages.append({"role": "assistant", "content": msg.content})
            return {
                "type": "final",
                "content": (getattr(msg, "content", None) or "").strip() or "실행 완료",
                "messages": messages,
                "seen_calls": list(seen),
                "steps_used": step,
                "used_tools": used_tools,
                "trace": trace,
            }

        calls_to_use = calls if allow_multiple_tool_calls else calls[:1]

        # stop-policy: pre-check first (like run_react_agent)
        if duplicate_policy == "stop":
            call = calls_to_use[0]
            name = call["name"]
            args = call.get("arguments") or {}

            if tool_names_allowlist is not None and name not in tool_names_allowlist:
                return {
                    "type": "final",
                    "content": unknown_tool_final_message(name),
                    "messages": messages,
                    "seen_calls": list(seen),
                    "steps_used": step,
                    "used_tools": used_tools,
                    "trace": trace,
                }

            sig = make_tool_call_sig(name, args)
            if sig in seen:
                return {
                    "type": "final",
                    "content": duplicate_final_message,
                    "messages": messages,
                    "seen_calls": list(seen),
                    "steps_used": step,
                    "used_tools": used_tools,
                    "trace": trace,
                }

            seen.add(sig)
            used_tools = True

            append_assistant_tool_calls(
                messages,
                content=getattr(msg, "content", None),
                tool_calls=[call],
                arguments_mode=arguments_mode,
            )

            # handoff (do not execute tool)
            if handoff_tools and name in handoff_tools:
                return {
                    "type": "handoff",
                    "tool_call": call,
                    "messages": messages,
                    "seen_calls": list(seen),
                    "steps_used": step,
                    "used_tools": used_tools,
                    "trace": trace,
                }

            observation = await call_tool_fn(name, args, ctx)

            # ✅ full 결과는 ctx에 저장
            store_tool_observation(
                ctx,
                tool_call_id=call["id"],
                tool_name=name,
                arguments=args,
                observation=observation,
            )

            # ✅ LLM에는 최소 ACK만 노출
            append_tool_result(
                messages,
                tool_call_id=call["id"],
                content=minimal_tool_ack(call["id"]),
            )
            continue

        # tool_error-policy: record assistant tool_calls first, then per-call execute
        used_tools = True
        append_assistant_tool_calls(
            messages,
            content=getattr(msg, "content", None),
            tool_calls=calls_to_use,
            arguments_mode=arguments_mode,
        )

        for call in calls_to_use:
            name = call["name"]
            args = call.get("arguments") or {}

            if tool_names_allowlist is not None and name not in tool_names_allowlist:
                append_tool_result(
                    messages,
                    tool_call_id=call["id"],
                    content=json.dumps(
                        {
                            "ok": False,
                            "error": "Unknown tool (not in allowlist).",
                            "tool": name,
                            "arguments": args,
                        },
                        ensure_ascii=False,
                    ),
                )
                continue

            sig = make_tool_call_sig(name, args)
            if sig in seen:
                append_tool_result(
                    messages,
                    tool_call_id=call["id"],
                    content=json.dumps(
                        {
                            "ok": False,
                            "error": "Duplicate tool call detected; stopping to avoid a loop.",
                            "tool": name,
                            "arguments": args,
                        },
                        ensure_ascii=False,
                    ),
                )
                continue

            seen.add(sig)
            observation = await call_tool_fn(name, args, ctx)

            store_tool_observation(
                ctx,
                tool_call_id=call["id"],
                tool_name=name,
                arguments=args,
                observation=observation,
            )

            append_tool_result(
                messages,
                tool_call_id=call["id"],
                content=minimal_tool_ack(call["id"]),
            )

    # max steps exceeded
    return {
        "type": "final",
        "content": max_steps_final_message,
        "messages": messages,
        "seen_calls": list(seen),
        "steps_used": int(start_step) + steps_left,
        "used_tools": used_tools,
        "trace": trace,
    }

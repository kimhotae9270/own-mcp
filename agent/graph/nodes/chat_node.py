import os
import json
from typing import Any, Dict, List, Tuple

from agent.llm.client import get_llm
from agent.graph.actions import ReactSession
from agent.graph.state import AgentState

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _extract_tool_observations(react_session: ReactSession | None) -> List[Dict[str, Any]]:
    if not react_session:
        return []

    messages = react_session.get("messages") or []
    if not isinstance(messages, list):
        return []

    id_to_call: Dict[str, Tuple[str, str]] = {}

    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls") or []
        if not tool_calls:
            continue
        for tc in tool_calls:
            try:
                call_id = tc.get("id")
                fn = (tc.get("function") or {})
                name = fn.get("name")
                args = fn.get("arguments")
                if not call_id or not name:
                    continue
                args_str = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
                id_to_call[str(call_id)] = (str(name), args_str)
            except Exception:
                continue

    out: List[Dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "tool":
            continue
        call_id = m.get("tool_call_id")
        if not call_id:
            continue
        name, args = id_to_call.get(str(call_id), ("(unknown_tool)", "{}"))
        out.append({"tool": name, "arguments": args, "result": m.get("content")})

    return out


async def chat_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]

    ctx = state.get("ctx", {}) or {}
    mem = (ctx.get("memory") or {}) if isinstance(ctx, dict) else {}
    summary = (mem.get("summary") or "").strip()
    recent = mem.get("recent") or []

    payload = state.get("route_payload") or {}
    react_session = payload.get("react_session") or state.get("react_session")
    tool_obs = _extract_tool_observations(react_session)

    llm = get_llm()

    system_parts: List[str] = ["""
        You are a helpful assistant.
        Do not call external tools in this node.
        Use the provided conversation context.
        If tool results are provided, treat them as authoritative facts.
        
        If tool outputs are long, summarize them before answering.
        Focus only on information relevant to the user's request.
        Avoid repeating raw tool output verbatim.
        Extract and present only the key facts, conclusions, or actionable items.
        Keep the final response concise unless the user explicitly asks for detailed output.
    """]

    if summary:
        system_parts.append("\n[Conversation summary]\n" + summary)

    if tool_obs:
        lines: List[str] = ["\n[Tool results from this request]"]
        for i, t in enumerate(tool_obs, start=1):
            lines.append(f"{i}) tool={t.get('tool')} args={t.get('arguments')}\nresult={t.get('result')}")
        system_parts.append("\n".join(lines))

    messages: List[Dict[str, Any]] = [{"role": "system", "content": "\n".join(system_parts)}]

    for m in recent:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": text})

    resp = await llm.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
    )

    answer = resp.choices[0].message.content or ""
    trace.append("chat_agent: answered")

    return {
        **state,
        "route": None,
        "route_payload": None,
        "react_session": None,
        "answer": answer,
        "trace": trace,
    }
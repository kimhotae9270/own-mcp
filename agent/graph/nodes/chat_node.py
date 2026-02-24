import os
import json
from typing import Any, Dict, List, Tuple



from agent.llm.client import get_llm
from agent.graph.actions import ReactSession
from agent.graph.state import AgentState
import re
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

def _clean_notice_title(title: str) -> str:
    """
    제목 앞의 [부서명] 제거
    ex) "[학생지원팀] 장학생 모집" → "장학생 모집"
    """
    if not title:
        return title
    # 맨 앞에 있는 [ ... ] 패턴 제거
    return re.sub(r"^\s*\[[^\]]+\]\s*", "", title).strip()

def _safe_to_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, ensure_ascii=False, default=str)
    except Exception:
        return str(x)


def _extract_tool_observations(
    react_session: ReactSession | None,
    ctx: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
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

    store = (ctx or {}).get("_tool_store") if isinstance(ctx, dict) else {}
    if not isinstance(store, dict):
        store = {}

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

        rec = store.get(str(call_id))
        if isinstance(rec, dict) and "result" in rec:
            result_text = _safe_to_text(rec.get("result"))
        else:
            result_text = _safe_to_text(m.get("content"))

        out.append({"tool": name, "arguments": args, "result": result_text})

    return out


# ---------------------------
# ✅ NEW: tool result compaction
# ---------------------------
def _truncate(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


def _try_parse_json(s: str) -> Any:
    if not s or not isinstance(s, str):
        return None
    s2 = s.strip()
    if not (s2.startswith("{") or s2.startswith("[")):
        return None
    try:
        return json.loads(s2)
    except Exception:
        return None



def _summarize_notice_list(obj: Any, max_items: int = 10) -> str | None:
    if not isinstance(obj, dict):
        return None
    data = obj.get("data")
    if not isinstance(data, list) or not data:
        return None

    lines: List[str] = []
    for i, it in enumerate(data[:max_items], start=1):
        if not isinstance(it, dict):
            continue

        raw_title = (it.get("title") or "").strip()
        title = _clean_notice_title(raw_title)

        if not title:
            continue

        # ✅ 여기서 실제로 lines에 넣어야 결과에 반영됨
        lines.append(f"{i}. {title}")

    if not lines:
        return None

    return "공지사항 목록(요약):\n" + "\n".join(lines)


def _compact_tool_observations(
    tool_obs: List[Dict[str, Any]],
    *,
    max_total_chars: int = 1200,
    per_tool_max_chars: int = 600,
) -> str:
    """
    툴 결과를 chat 노드에 넣기 전에 코드에서 최대한 압축한다.
    - JSON이면 파싱해서 도메인별 요약 시도
    - 길면 자르고, '원문 생략'만 남김
    """
    chunks: List[str] = []
    remaining = max_total_chars

    for t in tool_obs:
        tool = (t.get("tool") or "").strip()
        args = (t.get("arguments") or "").strip()
        raw = (t.get("result") or "").strip()

        parsed = _try_parse_json(raw)
        summary = None

        # 도메인별 요약: notice_list
        if tool == "notice_list" and parsed is not None:
            summary = _summarize_notice_list(parsed)

        body = summary if summary else raw
        body = _truncate(body, per_tool_max_chars)

        piece = f"[Tool: {tool} | args: {args}]\n{body}".strip()

        if remaining <= 0:
            break
        if len(piece) > remaining:
            piece = _truncate(piece, remaining)
        chunks.append(piece)
        remaining -= (len(piece) + 2)  # newline budget

    return "\n\n".join(chunks).strip()


async def chat_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]

    ctx = state.get("ctx", {}) or {}
    mem = (ctx.get("memory") or {}) if isinstance(ctx, dict) else {}
    summary = (mem.get("summary") or "").strip()
    recent = mem.get("recent") or []

    payload = state.get("route_payload") or {}
    react_session = payload.get("react_session") or state.get("react_session")
    tool_obs = _extract_tool_observations(react_session, ctx)

    llm = get_llm()

    # ✅ system은 "규칙"만 짧게
    system_prompt = (
        "You are a helpful assistant.\n"
        "Do not call external tools in this node.\n"
        "If tool results are provided, treat them as authoritative facts.\n"
        "Keep the final response concise unless the user explicitly asks for details.\n"
    )

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # ✅ 대화 요약은 system에 넣어도 되지만, 짧게 유지
    if summary:
        messages.append({"role": "assistant", "content": f"[Conversation summary]\n{_truncate(summary, 600)}"})

    # ✅ tool 결과는 system이 아니라 별도 assistant 컨텍스트로
    if tool_obs:
        compact = _compact_tool_observations(tool_obs)
        if compact:
            messages.append({"role": "assistant", "content": f"[Tool context]\n{compact}"})

    # ✅ recent 채팅 붙이기 (중복 user_text 방지)
    for m in recent:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})

    # 마지막 recent가 이미 같은 user_text면 중복 제거
    if messages and messages[-1]["role"] == "user":
        if (messages[-1].get("content") or "").strip() == (text or "").strip():
            pass
        else:
            messages.append({"role": "user", "content": text})
    else:
        messages.append({"role": "user", "content": text})

    import time
    t0 = time.perf_counter()
    print("chat node input\n ==========================================")
    print(messages)
    print("==========================================")
    resp = await llm.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
    )
    t1 = time.perf_counter()
    print(f"chat: llm_ms={(t1 - t0) * 1000:.1f}")

    answer = resp.choices[0].message.content or ""
    trace.append("chat_agent: answered")
    print(answer)
    return {
        **state,
        "route": None,
        "route_payload": None,
        "react_session": None,
        "answer": answer,
        "trace": trace,
    }
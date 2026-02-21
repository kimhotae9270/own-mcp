import json
from agent.graph.actions import ReactSession
from agent.graph.state import AgentState
from agent.tools.agents.run_calendar_agent import run_calendar_agent


def _looks_like_clarifying_question(text: str) -> bool:
    t = (text or "").strip()
    return t.endswith("?") or ("?" in t and ("몇" in t or "어느" in t or "언제" in t))


async def calendar_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    ctx = state.get("ctx", {})
    payload = state.get("route_payload") or {}

    user_text = payload.get("user_text") or state["user_text"]

    answer = await run_calendar_agent(user_text, ctx=ctx)
    trace.append("agent: answered via calendar agent")

    react_session: ReactSession | None = payload.get("react_session") or state.get("react_session")

    if not react_session:
        return {**state, "answer": answer, "trace": trace, "route": None, "route_payload": None, "react_session": None}

    messages = react_session.get("messages") or []
    seen_calls = react_session.get("seen_calls") or []
    steps_used = int(react_session.get("steps_used", 0))
    max_steps = int(react_session.get("max_steps", 6))

    tool_call_id = payload.get("tool_call_id")
    if not tool_call_id:
        pending = react_session.get("pending_tool_call") or {}
        tool_call_id = pending.get("id")

    tool_payload = {"calendar_answer": answer}

    if tool_call_id:
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(tool_payload, ensure_ascii=False),
            }
        )
    else:
        messages.append({"role": "assistant", "content": json.dumps(tool_payload, ensure_ascii=False)})

    next_session: ReactSession = {
        "messages": messages,
        "seen_calls": seen_calls,
        "steps_used": steps_used,
        "max_steps": max_steps,
    }
    return {
        **state,
        "answer": None,
        "trace": trace,
        "route": "REACT",
        "route_payload": None,
        "react_session": next_session,
    }
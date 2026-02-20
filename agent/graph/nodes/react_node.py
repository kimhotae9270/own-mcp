# agent/graph/nodes/react_node.py
import json
from agent.graph.state import AgentState
from agent.tools.agents.run_react_agent import run_react_agent, CALENDAR_ROUTE_SENTINEL


async def react_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]
    ctx = state.get("ctx", {})

    # ✅ 캘린더 노드 후 ReAct 재개를 위한 session
    react_session = state.get("react_session") or {}
    resume_messages = react_session.get("messages")
    resume_seen_calls = react_session.get("seen_calls")
    resume_steps_used = react_session.get("steps_used", 0)

    answer, react_trace = await run_react_agent(
        text=text,
        ctx=ctx,
        max_steps=6,
        resume_messages=resume_messages,
        resume_seen_calls=resume_seen_calls,
        resume_steps_used=resume_steps_used,
    )
    trace.extend(react_trace)

    # ✅ ReAct가 캘린더 tool을 선택하면: 실행하지 않고 캘린더 노드로 handoff
    if isinstance(answer, str) and answer.startswith(CALENDAR_ROUTE_SENTINEL):
        payload = None
        if "::" in answer:
            _, raw = answer.split("::", 1)
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"_raw": raw}

        next_react_session = None
        if isinstance(payload, dict):
            next_react_session = payload.get("react_session")

        return {
            **state,
            "route": "CALENDAR",
            "route_payload": payload,          # tool_name/tool_args/user_text/react_session
            "react_session": next_react_session,
            "answer": None,
            "trace": trace,
        }

    # 정상 종료면 route/session 정리
    return {
        **state,
        "route": None,
        "route_payload": None,
        "react_session": None,
        "answer": answer,
        "trace": trace,
    }
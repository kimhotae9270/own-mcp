from agent.graph.actions import ReactSession
from agent.graph.state import AgentState
from agent.tools.agents.run_react_agent import run_react_agent


async def react_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]
    ctx = state.get("ctx", {})
    react_session: ReactSession = state.get("react_session") or {}

    action = await run_react_agent(
        text=text,
        ctx=ctx,
        max_steps=6,
        resume_messages=react_session.get("messages"),
        resume_seen_calls=react_session.get("seen_calls"),
        resume_steps_used=react_session.get("steps_used", 0),
    )

    if action.get("trace"):
        trace.extend(action["trace"])

    if action["type"] == "handoff":
        payload = action["payload"]
        return {
            **state,
            "route": action["route"],          # "CALENDAR"
            "route_payload": payload,
            "react_session": payload.get("react_session"),
            "answer": None,
            "trace": trace,
        }

    # ✅ 도구를 안 썼든/썼든 최종 자연어 응답은 CHAT 노드에서 생성
    return {
        **state,
        "route": "CHAT",
        "route_payload": {
            "react_session": action.get("react_session"),
            "react_draft": action.get("answer"),
            "used_tools": action.get("used_tools"),
        },
        "react_session": action.get("react_session"),
        "answer": None,
        "trace": trace,
    }
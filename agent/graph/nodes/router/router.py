# graph/router/router.py
from agent.graph.state import AgentState
from .llm_fallback import llm_fallback_route

async def router_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]
    mode = state.get("mode") or "AUTO"

    # 1) 강제 모드 유지
    if mode == "CHAT":
        trace.append("router: forced CHAT")
        return {**state, "route": "CHAT", "trace": trace}

    if mode == "CALENDAR":
        trace.append("router: forced CALENDAR")
        return {**state, "route": "CALENDAR", "trace": trace}

    # 2) AUTO: 캘린더-only면 CALENDAR, 아니면 REACT
    route = await llm_fallback_route(text)
    trace.append(f"router: llm route -> {route}")
    return {**state, "route": route, "trace": trace}
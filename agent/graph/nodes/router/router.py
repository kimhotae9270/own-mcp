# graph/router/router.py
from agent.graph.state import AgentState

# mode 값이 없거나 AUTO면 기본으로 REACT로 보냄
DEFAULT_ROUTE = "REACT"

# 허용되는 모드(원하는 만큼 추가 가능)
MODE_TO_ROUTE = {
    "REACT": "REACT",
    "CALENDAR": "CALENDAR",
    "CHAT": "CHAT",
    # 나중에 필요하면:
    # "NOTICE": "NOTICE",
    # "DRIVE": "DRIVE",
}

async def router_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    mode = (state.get("mode") or "AUTO").upper()

    if mode in MODE_TO_ROUTE:
        route = MODE_TO_ROUTE[mode]
        trace.append(f"router: mode -> {route}")
        return {**state, "route": route, "trace": trace}

    # AUTO/미지정/알 수 없는 mode는 전부 REACT
    trace.append(f"router: mode={mode} -> default {DEFAULT_ROUTE}")

    return {**state, "route": DEFAULT_ROUTE, "trace": trace}
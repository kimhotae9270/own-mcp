from mcp_app.graph.state import AgentState


async def router_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]
    mode = state.get("mode") or "AUTO"

    if mode == "CHAT":
        trace.append("router: forced CHAT")
        return {**state, "route": "CHAT", "trace": trace}

    if mode == "MCP":
        trace.append("router: forced MCP")
        return {**state, "route": "MCP", "trace": trace}

    # AUTO: 빠른 휴리스틱
    hint_keywords = ["계산", "곱", "나눠", "더해", "빼", "도구", "툴", "mcp", "실행", "정확히"]
    if any(k in text for k in hint_keywords):
        trace.append("router: heuristic -> MCP")
        return {**state, "route": "MCP", "trace": trace}

    trace.append("router: heuristic -> CHAT")
    return {**state, "route": "CHAT", "trace": trace}

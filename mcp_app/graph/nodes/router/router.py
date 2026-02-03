# graph/router/router.py

from mcp_app.graph.state import AgentState
from .heuristics import heuristic_route
from .embedding_route import embedding_route
from .llm_fallback import llm_fallback_route


async def router_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]
    mode = state.get("mode") or "AUTO"


    # 1. 강제 모드
    if mode == "CHAT":
        trace.append("router: forced CHAT")
        return {**state, "route": "CHAT", "trace": trace}

    if mode == "SUMMARY_MCP":
        trace.append("router: forced SUMMARY_MCP")
        return {**state, "route": "SUMMARY_MCP", "trace": trace}

    # 2. heuristic
    route = heuristic_route(text)
    if route:
        trace.append(f"router: heuristic -> {route}")
        return {**state, "route": route, "trace": trace}

    #3. embedding
    route, tool, score = embedding_route(text)
    trace.append(f"router: embedding score={score:.3f}, tool={tool}")

    if route:
        trace.append("router: embedding -> SUMMARY_MCP")
        return {
            **state,
            "route": route,
            "mcp_candidate": tool,
            "trace": trace,
       }

    route = await llm_fallback_route(text)
    trace.append(f"router: llm fallback -> {route}")

    return {
        **state,
        "route": route,
        "trace": trace,
    }

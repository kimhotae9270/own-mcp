from langgraph.graph import StateGraph, END

from mcp_app.graph.state import AgentState
from mcp_app.graph.nodes.router.router import router_node
from mcp_app.graph.nodes.chat import chat_agent_node
from mcp_app.graph.nodes.mcp import mcp_agent_node


def route_selector(state: AgentState) -> str:
    return state.get("route", "CHAT")


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router", router_node)
    g.add_node("CHAT", chat_agent_node)
    g.add_node("SUMMARY_MCP", mcp_agent_node)

    g.set_entry_point("router")

    g.add_conditional_edges(
        "router",
        route_selector,
        {
            "CHAT": "CHAT",
            "SUMMARY_MCP": "SUMMARY_MCP",
        },
    )

    g.add_edge("CHAT", END)
    g.add_edge("SUMMARY_MCP", END)

    return g.compile()


graph_app = build_graph()

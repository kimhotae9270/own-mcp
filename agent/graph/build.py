from langgraph.graph import StateGraph, END

from agent.graph.state import AgentState
from agent.graph.nodes.router.router import router_node
from agent.graph.nodes.chat import chat_agent_node
from agent.graph.nodes.calendar_mcp import calendar_agent_node


def route_selector(state: AgentState) -> str:
    return state.get("route", "CHAT")


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router", router_node)
    g.add_node("CHAT", chat_agent_node)
    g.add_node("CALENDAR", calendar_agent_node)

    g.set_entry_point("router")

    g.add_conditional_edges(
        "router",
        route_selector,
        {
            "CHAT": "CHAT",
            "CALENDAR": "CALENDAR",
        },
    )

    g.add_edge("CHAT", END)
    g.add_edge("CALENDAR", END)

    return g.compile()


graph_app = build_graph()

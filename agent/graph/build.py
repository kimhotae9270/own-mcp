from langgraph.graph import StateGraph, END

from agent.graph.state import AgentState
from agent.graph.nodes.router.router import router_node
from agent.graph.nodes.chat_node import chat_agent_node
from agent.graph.nodes.calendar_node import calendar_agent_node
from agent.graph.nodes.react_node import react_agent_node


def route_selector(state: AgentState) -> str:
    return state.get("route", "router")


def next_route_or_end(state: AgentState) -> str:
    return state.get("route") or "END"


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router", router_node)
    g.add_node("CHAT", chat_agent_node)
    g.add_node("CALENDAR", calendar_agent_node)
    g.add_node("REACT", react_agent_node)

    g.set_entry_point("router")

    g.add_conditional_edges(
        "router",
        route_selector,
        {
            "CHAT": "CHAT",
            "CALENDAR": "CALENDAR",
            "REACT": "REACT",
        },
    )

    g.add_conditional_edges(
        "REACT",
        next_route_or_end,
        {
            "CALENDAR": "CALENDAR",
            "CHAT": "CHAT",
            "END": END,
        },
    )

    g.add_conditional_edges(
        "CALENDAR",
        next_route_or_end,
        {
            "REACT": "REACT",
            "CHAT": "CHAT",
            "END": END,
        },
    )

    g.add_edge("CHAT", END)

    return g.compile()


graph_app = build_graph()
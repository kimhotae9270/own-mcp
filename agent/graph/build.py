# build.py
from langgraph.graph import StateGraph, END

from agent.graph.state import AgentState
from agent.graph.nodes.router.router import router_node
from agent.graph.nodes.chat import chat_agent_node
from agent.graph.nodes.calendar_node import calendar_agent_node
from agent.graph.nodes.react_node import react_agent_node  # ✅ 새로 추가

def route_selector(state: AgentState) -> str:
    return state.get("route", "REACT")

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router", router_node)
    g.add_node("CHAT", chat_agent_node)
    g.add_node("CALENDAR", calendar_agent_node)
    g.add_node("REACT", react_agent_node)  # ✅ 새로 추가

    g.set_entry_point("router")

    g.add_conditional_edges(
        "router",
        route_selector,
        {
            "CHAT": "CHAT",
            "CALENDAR": "CALENDAR",
            "REACT": "REACT",  # ✅
        },
    )

    g.add_edge("CHAT", END)
    g.add_edge("CALENDAR", END)
    g.add_edge("REACT", END)

    return g.compile()

graph_app = build_graph()
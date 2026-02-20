# agent/graph/nodes/react_node.py
import json
from agent.graph.state import AgentState
from agent.tools.agents.run_react_agent import run_react_agent, CALENDAR_ROUTE_SENTINEL

async def react_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]
    ctx = state.get("ctx", {})

    answer, react_trace = await run_react_agent(text=text, ctx=ctx, max_steps=6)
    trace.extend(react_trace)

    # A안: ReAct가 캘린더 툴을 "선택"하면, 실행은 캘린더 노드로 handoff
    if isinstance(answer, str) and answer.startswith(CALENDAR_ROUTE_SENTINEL):
        payload = None
        if "::" in answer:
            _, raw = answer.split("::", 1)
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"_raw": raw}
        return {
            **state,
            "route": "CALENDAR",
            "route_payload": payload,
            "answer": None,
            "trace": trace,
        }

    return {**state, "answer": answer, "trace": trace}

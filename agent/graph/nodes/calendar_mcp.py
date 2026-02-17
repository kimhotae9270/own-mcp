from agent.graph.state import AgentState
from agent.tools.agents.run_calendar_agent import run_calendar_agent  # 다음 단계에서 만들 파일


async def calendar_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]
    ctx = state.get("ctx", {})
    answer = await run_calendar_agent(text,ctx=ctx)

    trace.append("agent: answered via calendar tools")
    return {**state, "answer": answer, "trace": trace}

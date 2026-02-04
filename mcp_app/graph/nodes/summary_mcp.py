from mcp_app.graph.state import AgentState
from mcp_app.tools.run_summary_agent import run_summary_agent  # 다음 단계에서 만들 파일


async def summary_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]

    answer = await run_summary_agent(text)

    trace.append("mcp_agent: answered via MCP tools")
    return {**state, "answer": answer, "trace": trace}

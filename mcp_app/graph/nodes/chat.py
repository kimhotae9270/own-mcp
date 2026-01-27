import os
from openai import AsyncOpenAI

from mcp_app.graph.state import AgentState

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
oai = AsyncOpenAI()


async def chat_agent_node(state: AgentState) -> AgentState:
    trace = state.get("trace", [])
    text = state["user_text"]

    resp = await oai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Do not use external tools."},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )

    answer = resp.choices[0].message.content or ""
    trace.append("chat_agent: answered")
    return {**state, "answer": answer, "trace": trace}

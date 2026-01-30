from mcp_app.graph.state import AgentState
from ..embedding.client import embed
from ..embedding.similarity import cosine
from ..embedding.loader import load_mcp_embeddings
import re

URL_PATTERN = re.compile(r"https?://\S+")


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
    hint_keywords = ["요약", "링크", "분석", "유튜브", "논문", "도구", "영상"]
    if any(k in text for k in hint_keywords):
        trace.append("router: heuristic -> MCP")
        return {**state, "route": "MCP", "trace": trace}

    mcp_embeddings = load_mcp_embeddings()
    clean_text = URL_PATTERN.sub("", text).strip()

    query_embedding = embed(clean_text)

    best_tool = None
    best_score = 0.0

    for tool_name, tool_embedding in mcp_embeddings.items():
        score = cosine(query_embedding, tool_embedding)
        if score > best_score:
            best_tool = tool_name
            best_score = score

    trace.append(
        f"router: embedding score={best_score:.3f}, tool={best_tool}"
    )

    if best_score >= 0.35:

        trace.append("router: embedding -> MCP")
        return {
            **state,
            "route": "MCP",
            "mcp_candidate": best_tool,  # 다음 노드에서 참고 가능
            "trace": trace,
        }


    else:
        trace.append("router: heuristic -> CHAT")
        return {**state, "route": "CHAT", "trace": trace}

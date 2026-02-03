# graph/router/embedding_route.py

from mcp_app.embedding.client import embed
from mcp_app.embedding.similarity import cosine
from mcp_app.embedding.loader import load_mcp_embeddings
from .constants import EMBEDDING_THRESHOLD
import re

URL_PATTERN = re.compile(r"https?://\S+")

def embedding_route(text: str) -> tuple[str | None, str | None, float]:
    clean_text = URL_PATTERN.sub("", text).strip()
    query_embedding = embed(clean_text)

    mcp_embeddings = load_mcp_embeddings()

    best_tool = None
    best_score = 0.0

    for tool_name, tool_embedding in mcp_embeddings.items():
        score = cosine(query_embedding, tool_embedding)
        if score > best_score:
            best_tool = tool_name
            best_score = score

    if best_score >= EMBEDDING_THRESHOLD:
        return "SUMMARY_MCP", best_tool, best_score

    return None, None, best_score

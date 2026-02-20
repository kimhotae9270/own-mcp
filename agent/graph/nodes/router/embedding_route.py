# graph/router/embedding_route.py

from agent.embedding.client import embed
from agent.embedding.similarity import cosine
from agent.embedding.loader import load_mcp_embeddings
import re
from typing import List, Dict, Any, Tuple

URL_PATTERN = re.compile(r"https?://\S+")

def embedding_route_topk(text: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    반환 예:
      [
        {"tool": "calendar.list", "score": 0.82},
        {"tool": "calendar.create", "score": 0.77},
        ...
      ]
    """
    clean_text = URL_PATTERN.sub("", text).strip()
    query_embedding = embed(clean_text)
    mcp_embeddings = load_mcp_embeddings()  # {tool_name: embedding}

    scored: List[Tuple[str, float]] = []
    for tool_name, tool_embedding in mcp_embeddings.items():
        score = cosine(query_embedding, tool_embedding)
        scored.append((tool_name, float(score)))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[: max(1, k)]

    return [{"tool": name, "score": score} for name, score in top]
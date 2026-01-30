from pathlib import Path
from .client import embed
from . import cache
from .config import EMBEDDING_META

PROMPT_DIR = "C:/Users/아이씨티웨이/PycharmProjects/PythonProject2/mcp_app/graph/prompts"

def load_mcp_embeddings() -> dict[str, list[float]]:

    # 이미 로딩되어 있으면 그대로 사용
    if cache.MCP_EMBEDDINGS and cache.MCP_EMBEDDING_META == EMBEDDING_META:
        return cache.MCP_EMBEDDINGS

    cache.MCP_EMBEDDINGS.clear()

    for path in Path(PROMPT_DIR).glob("*.prompt"):
        tool_name = path.stem
        text = path.read_text(encoding="utf-8")
        cache.MCP_EMBEDDINGS[tool_name] = embed(text)

    cache.MCP_EMBEDDING_META = EMBEDDING_META.copy()

    return cache.MCP_EMBEDDINGS

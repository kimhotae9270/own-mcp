from pathlib import Path
from .client import embed
from .cache import MCP_EMBEDDINGS, MCP_EMBEDDING_META
from .config import EMBEDDING_META

PROMPT_DIR = "C:/Users/아이씨티웨이/PycharmProjects/PythonProject2/mcp_app/graph/prompts"

def load_mcp_embeddings() -> dict[str, list[float]]:
    global MCP_EMBEDDINGS, MCP_EMBEDDING_META

    # 이미 로딩되어 있으면 그대로 사용
    if MCP_EMBEDDINGS and MCP_EMBEDDING_META == EMBEDDING_META:
        return MCP_EMBEDDINGS

    MCP_EMBEDDINGS.clear()

    for path in Path(PROMPT_DIR).glob("*.prompt"):
        tool_name = path.stem
        text = path.read_text(encoding="utf-8")
        MCP_EMBEDDINGS[tool_name] = embed(text)

    MCP_EMBEDDING_META = EMBEDDING_META.copy()

    return MCP_EMBEDDINGS

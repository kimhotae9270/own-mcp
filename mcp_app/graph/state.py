from typing import TypedDict, Optional, Literal, List


class AgentState(TypedDict, total=False):
    user_text: str
    mode: Optional[Literal["AUTO", "CHAT", "MCP"]]
    route: Optional[Literal["CHAT", "MCP"]]
    answer: Optional[str]
    trace: List[str]

from typing import TypedDict, Optional, Literal, List


class AgentState(TypedDict, total=False):
    user_text: str
    mode: Optional[Literal["AUTO", "CHAT", "SUMMARY_MCP"]]
    route: Optional[Literal["CHAT", "SUMMARY_MCP"]]
    answer: Optional[str]
    trace: List[str]

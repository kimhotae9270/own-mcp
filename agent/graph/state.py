from typing import TypedDict, Optional, Literal, List,Dict,Any


class AgentState(TypedDict, total=False):
    user_text: str
    mode: Optional[Literal["AUTO", "CHAT", "CALENDAR"]]
    route: Optional[Literal["CHAT", "CALENDAR"]]
    answer: Optional[str]
    trace: List[str]
    ctx: Dict[str, Any]

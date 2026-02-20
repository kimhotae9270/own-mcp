# graph/router/state.py (또는 agent/graph/state.py에 해당한다면 그 파일)
from typing import TypedDict, Optional, Literal, List, Dict, Any


class AgentState(TypedDict, total=False):
    user_text: str
    mode: Optional[Literal["AUTO", "CHAT", "CALENDAR"]]

    # route 확장: REACT 추가
    route: Optional[Literal["CHAT", "CALENDAR", "REACT"]]

    answer: Optional[str]
    trace: List[str]
    ctx: Dict[str, Any]

    # router가 채워주는 Top-K 후보
    tool_candidates: List[Dict[str, Any]]
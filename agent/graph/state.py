"""graph/router/state.py (or agent/graph/state.py)

AgentState is the single state object that flows through the graph/router.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict, TYPE_CHECKING

try:  # Python 3.11+
    from typing import NotRequired
except ImportError:  # pragma: no cover
    from typing_extensions import NotRequired

from agent.graph.schemas import ReactSession


class AgentState(TypedDict, total=False):
    user_text: str
    mode: Optional[Literal["AUTO", "CHAT", "CALENDAR", "REACT"]]
    route: Optional[Literal["CHAT", "CALENDAR", "REACT"]]

    # NOTE: graph 노드들에서 `None`을 넣는 케이스가 많아서 Optional로 둡니다.
    route_payload: NotRequired[Optional[Dict[str, Any]]]

    answer: NotRequired[Optional[str]]
    trace: NotRequired[List[str]]
    ctx: NotRequired[Dict[str, Any]]

    used_tools: NotRequired[bool]

    # REACT의 세션 스키마는 actions.ReactSession을 따라가야 type-check 경고가 안 납니다.
    react_session: NotRequired[Optional["ReactSession"]]
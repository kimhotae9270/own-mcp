"""agent/graph/actions.py

Agent graph action / session schemas.

Why this file matters:
- `run_react_agent.py` returns `FinalAction` with extra metadata
  (`used_tools`, `react_session`). Those keys must exist in the schema.
- During a calendar handoff, REACT needs to remember the pending tool call
  (`pending_tool_call`) so the session can be resumed correctly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict

try:  # Python 3.11+
    from typing import NotRequired
except ImportError:  # pragma: no cover
    from typing_extensions import NotRequired

from agent.graph.schemas import ReactSession  # ✅ 여기로 이동

class PendingToolCall(TypedDict):
    id: str
    name: str
    arguments: Dict[str, Any]


class FinalAction(TypedDict):
    type: Literal["final"]
    answer: str
    trace: Optional[List[str]]
    used_tools: NotRequired[bool]
    react_session: NotRequired[ReactSession]


class HandoffAction(TypedDict):
    type: Literal["handoff"]
    route: Literal["CHAT", "CALENDAR", "REACT"]
    payload: Dict[str, Any]
    trace: Optional[List[str]]


Action = FinalAction | HandoffAction
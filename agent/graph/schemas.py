# agent/graph/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, TypedDict

try:  # Python 3.11+
    from typing import NotRequired
except ImportError:  # pragma: no cover
    from typing_extensions import NotRequired


class PendingToolCall(TypedDict):
    id: str
    name: str
    arguments: Dict[str, Any]


class ReactSession(TypedDict, total=False):
    messages: List[Dict[str, Any]]
    seen_calls: List[str]
    steps_used: int
    max_steps: int
    pending_tool_call: NotRequired[PendingToolCall]
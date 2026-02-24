from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union
from pydantic import BaseModel
from .policy import REACT_EXCLUDE_TOOLS, REACT_EXCLUDE_TAGS
ToolFn = Callable[..., Union[Any, Awaitable[Any]]]

@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    tags: List[str]
    input_model: Type[BaseModel]
    handler: ToolFn

_REG: Dict[str, ToolDef] = {}

def register_tool(*, name: str, description: str, input_model: Type[BaseModel], tags: Optional[List[str]] = None):
    if tags is None:
        tags = []
    def deco(fn: ToolFn):
        _REG[name] = ToolDef(name, description.strip(), tags, input_model, fn)
        return fn
    return deco

def get_tools_by_tags(tags: List[str]) -> List[ToolDef]:
    want = {t.lower() for t in tags}
    return [t for t in _REG.values() if any(x.lower() in want for x in t.tags)]

def list_tools() -> List[ToolDef]:
    return list(_REG.values())

async def call_tool(name: str, args: dict, ctx: dict) -> Any:
    t = _REG[name]
    parsed = t.input_model.model_validate(args)
    res = t.handler(parsed, ctx)
    if hasattr(res, "__await__"):
        res = await res
    return res
def set_excluded_tools(names: Optional[List[str]] = None, tags: Optional[List[str]] = None) -> None:
    if names:
        REACT_EXCLUDE_TOOLS.update(names)
    if tags:
        REACT_EXCLUDE_TAGS.update([t.lower() for t in tags])

def list_tools_filtered(*, exclude_names: Optional[List[str]] = None, exclude_tags: Optional[List[str]] = None) -> List[ToolDef]:
    name_block = set(exclude_names or []) | REACT_EXCLUDE_TOOLS
    tag_block = {t.lower() for t in (exclude_tags or [])} | REACT_EXCLUDE_TAGS

    out: List[ToolDef] = []
    for t in _REG.values():
        if t.name in name_block:
            continue
        if tag_block and any(tag.lower() in tag_block for tag in t.tags):
            continue
        out.append(t)
    return out

class HandoffCalendarInput(BaseModel):
    user_text: str

@register_tool(
    name="handoff_calendar_agent",
    description=(
        "If the user request is about calendars, schedules, events, or time-based task management, "
        "you MUST call this tool.\n\n"

        "Use this tool when the user wants to:\n"
        "- Add, create, register, or schedule an event\n"
        "- Modify, update, or edit an existing event\n"
        "- Delete or cancel an event\n"
        "- List, show, or check scheduled events\n"
        "- Ask what is scheduled on a specific date or time\n\n"

        "DO NOT answer directly in natural language for calendar-related requests.\n"
        "Instead, immediately call this tool.\n\n"

        "Do NOT call this tool for general date questions, time calculations, "
        "or non-calendar informational queries."
    ),
    input_model=HandoffCalendarInput,
    tags=["handoff", "routing"],
)
def _handoff_calendar_agent(inp: HandoffCalendarInput, ctx: dict):
    # 실제 실행은 calendar_node에서 run_calendar_agent로 처리
    return {
        "_handoff": True,
        "route": "CALENDAR",
        "payload": {
            "user_text": inp.user_text,
        },
    }
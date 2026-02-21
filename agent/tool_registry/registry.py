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
        "캘린더/일정 관련 요청이면 이 도구를 호출하세요. "
        "이 도구는 ReAct에서 캘린더 전용 에이전트 노드로 라우팅하기 위한 핸드오프 신호를 만듭니다."
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
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union
from pydantic import BaseModel

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

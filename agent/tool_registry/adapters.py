from typing import List, Dict, Any
from .registry import ToolDef

def tools_to_openai_tools(tools: List[ToolDef]) -> List[Dict[str, Any]]:
    return [{
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.input_model.model_json_schema(),
        }
    } for t in tools]

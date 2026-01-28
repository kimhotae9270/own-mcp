# llm/call.py
from __future__ import annotations
from typing import List, Dict, Optional
import json
import httpx

from .config import load_llm_config, LLMConfig

class LLMNotConfigured(RuntimeError):
    pass

async def chat(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
    timeout: int = 120,
) -> str:
    cfg: Optional[LLMConfig] = load_llm_config()
    if cfg is None:
        raise LLMNotConfigured("LLM 설정이 없습니다. OPENAI_API_KEY/OPENAI_COMPAT_BASE_URL/OPENAI_MODEL 확인.")

    use_model = model or cfg.model
    url = f"{cfg.base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    payload = {
        "model": use_model,
        "messages": messages,
        "temperature": temperature,
    }

    # timeout은 httpx.Timeout으로 명시 가능
    t = httpx.Timeout(timeout)

    async with httpx.AsyncClient(timeout=t) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]

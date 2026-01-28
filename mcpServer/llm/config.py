# llm/config.py
from dataclasses import dataclass
from typing import Optional
import os

@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str

_LLM_CONFIG: Optional[LLMConfig] = None  # 🔥 singleton cache

def load_llm_config(force_reload: bool = False) -> Optional[LLMConfig]:
    global _LLM_CONFIG

    if _LLM_CONFIG is not None and not force_reload:
        return _LLM_CONFIG

    base_url = (os.getenv("OPENAI_COMPAT_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    if not api_key:
        _LLM_CONFIG = None
        return None

    _LLM_CONFIG = LLMConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    return _LLM_CONFIG

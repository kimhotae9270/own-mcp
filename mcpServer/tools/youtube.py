# tools/youtube.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import asyncio
import httpx
from fastmcp import FastMCP
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from youtube_transcript_api._errors import NoTranscriptFound

_YT_ID_RE = re.compile(
    r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:\?|&|$)"
)




def _extract_video_id(url: str) -> str:
    m = _YT_ID_RE.search(url)
    if not m:
        raise ValueError("Could not extract YouTube video id (expected 11-char id).")
    return m.group(1)

def merge_segments_by_time(segments, window_sec=60): #60초 병합
    chunks = []
    current = []
    start_time = None

    for seg in segments:
        if start_time is None:
            start_time = seg["start"]

        if seg["start"] - start_time <= window_sec:
            current.append(seg)
        else:
            text = " ".join(s["text"] for s in current)
            chunks.append({"start": start_time, "text": text})
            current = [seg]
            start_time = seg["start"]

    if current:
        text = " ".join(s["text"] for s in current)
        chunks.append({"start": start_time, "text": text})
    print(chunks)
    return chunks


def is_meaningful_chunk(text: str) -> bool: #의미 없는 청크 필터
    text = text.strip()

    if len(text) < 40:
        return False

    if len(text.split()) < 6:
        return False
    return True

async def summarize_chunk_short(cfg: LLMConfig, chunk_text: str) -> str:
    system = (
        "You summarize a short YouTube transcript segment.\n"
        "Rules:\n"
        "- Output EXACTLY one sentence.\n"
        "- Maximum 60 tokens.\n"
        "- Describe only the main point.\n"
        "- No explanations."
    )

    payload = {
        "model": cfg.model,  # gpt-4o-mini
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": chunk_text},
        ],
        "temperature": 0.2,
    }

    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

async def summarize_highlights(cfg: LLMConfig, highlights):
    system = (
        "You create a concise highlight summary of a YouTube video.\n"
        "Output valid JSON with keys: title, highlights.\n"
        "highlights must be bullet-style short sentences."
    )

    content = "\n".join(
        f"- ({h['start']}s) {h['summary']}"
        for h in highlights
    )

    payload = {
        "model": cfg.model, #.replace("mini", ""),  # gpt-4o 권장
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "temperature": 0.3,
    }

    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}"}

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        print(r.json()["choices"][0]["message"]["content"])
        return r.json()["choices"][0]["message"]["content"]


def _fetch_transcript_text(video_id: str, languages: Optional[List[str]] = None) -> Dict[str, Any]:
    ytt = YouTubeTranscriptApi()

    # 1) 우선순위 언어 리스트 구성
    preferred = languages[:] if languages else []
    # 기본 fallback 우선순위(한국 영상 많으면 ko를 앞에 두는 게 편함)
    for code in ["ko", "en"]:
        if code not in preferred:
            preferred.append(code)

    # 2) 먼저 preferred로 fetch 시도
    try:
        fetched = ytt.fetch(video_id, languages=preferred)
    except NoTranscriptFound:
        # 3) 그래도 없으면, 영상에 실제로 있는 언어를 조회해서 fallback
        transcript_list = ytt.list(video_id)

        # 우선: generated ko -> any generated -> any manual
        try:
            t = transcript_list.find_generated_transcript(["ko"])
        except Exception:
            t = None

        if t is None:
            # 아무 generated 하나
            for tr in transcript_list:
                if getattr(tr, "is_generated", False):
                    t = tr
                    break

        if t is None:
            # 마지막 fallback: 아무 manual 하나
            for tr in transcript_list:
                if not getattr(tr, "is_generated", False):
                    t = tr
                    break

        if t is None:
            # 진짜 아무것도 없으면 그대로 에러
            raise

        fetched = t.fetch()

    raw = fetched.to_raw_data()
    segments = [
        {
            "text": s.get("text", ""),
            "start": float(s.get("start", 0.0)),
            "duration": float(s.get("duration", 0.0)),
        }
        for s in raw
        if s.get("text")
    ]
    text = "\n".join(s["text"] for s in segments).strip()

    meta = {
        "video_id": getattr(fetched, "video_id", video_id),
        "language": getattr(fetched, "language", None),
        "language_code": getattr(fetched, "language_code", None),
        "is_generated": getattr(fetched, "is_generated", None),
    }

    return {"text": text, "segments": segments, "meta": meta}


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str


def _load_llm_config() -> Optional[LLMConfig]:
    """
    OpenAI-compatible Chat Completions endpoint:
    - BASE_URL: e.g. https://api.openai.com/v1  or http://localhost:8000/v1
    - API_KEY: token
    - MODEL: e.g. gpt-4o-mini / qwen2.5 / etc
    """
    base_url = os.getenv("OPENAI_COMPAT_BASE_URL", "").strip() or "https://api.openai.com/v1"
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"

    if not api_key:
        return None
    return LLMConfig(base_url=base_url, api_key=api_key, model=model)






def register_youtube_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def youtube_summarize(url: str) -> dict:
        vid = _extract_video_id(url)
        tr = _fetch_transcript_text(vid)

        llm_cfg = _load_llm_config()
        if llm_cfg is None:
            raise RuntimeError("OPENAI_API_KEY is required")

        # 1️⃣ 60초 병합
        rough_chunks = merge_segments_by_time(tr["segments"], window_sec=60)

        # 2️⃣ 의미 있는 청크만 필터
        valid_chunks = [
            c for c in rough_chunks
            if is_meaningful_chunk(c["text"])
        ]

        # 3️⃣ 병렬 초단 요약 (Map)
        tasks = [
            summarize_chunk_short(llm_cfg, c["text"])
            for c in valid_chunks
        ]
        summaries = await asyncio.gather(*tasks)

        highlights = [
            {"start": c["start"], "summary": s}
            for c, s in zip(valid_chunks, summaries)
        ]

        # 4️⃣ 상위 몇 개만 사용 (예: 앞에서 5개)
        top_highlights = highlights[:5]

        # 5️⃣ 하이라이트 묶기 (Reduce)
        final_summary = await summarize_highlights(llm_cfg, top_highlights)

        return {
            "video_id": vid,
            "highlights": highlights,
            "final_summary": final_summary,
        }

# tools/youtube.py
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import asyncio

from fastmcp import FastMCP
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound

from llm.config import load_llm_config, LLMConfig
from llm.call import chat, LLMNotConfigured  # 네가 chat_async -> chat 로 바꿨다고 했으니 chat 사용

_YT_ID_RE = re.compile(r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:\?|&|$)")

# ✅ 속도 튜닝 파라미터(환경변수로 조절)
YT_LLM_PARALLEL = int(os.getenv("YT_LLM_PARALLEL", "6"))      # 동시 호출 수
YT_WINDOW_SEC = int(os.getenv("YT_WINDOW_SEC", "90"))         # 병합 윈도우(초)
YT_MAX_CHUNKS = int(os.getenv("YT_MAX_CHUNKS", "8"))          # 요약할 청크 개수 상한


def _extract_video_id(url: str) -> str:
    m = _YT_ID_RE.search(url)
    if not m:
        raise ValueError("Could not extract YouTube video id (expected 11-char id).")
    return m.group(1)


def merge_segments_by_time(segments, window_sec=60):
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

    return chunks


def is_meaningful_chunk(text: str) -> bool:
    text = text.strip()
    if len(text) < 40:
        return False
    if len(text.split()) < 6:
        return False
    return True


def _fetch_transcript_text(video_id: str, languages: Optional[List[str]] = None) -> Dict[str, Any]:
    ytt = YouTubeTranscriptApi()

    preferred = languages[:] if languages else []
    for code in ["ko", "en"]:
        if code not in preferred:
            preferred.append(code)

    try:
        fetched = ytt.fetch(video_id, languages=preferred)
    except NoTranscriptFound:
        transcript_list = ytt.list(video_id)

        # 우선: generated ko -> any generated -> any manual
        try:
            t = transcript_list.find_generated_transcript(["ko"])
        except Exception:
            t = None

        if t is None:
            for tr in transcript_list:
                if getattr(tr, "is_generated", False):
                    t = tr
                    break

        if t is None:
            for tr in transcript_list:
                if not getattr(tr, "is_generated", False):
                    t = tr
                    break

        if t is None:
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

    meta = {
        "video_id": getattr(fetched, "video_id", video_id),
        "language": getattr(fetched, "language", None),
        "language_code": getattr(fetched, "language_code", None),
        "is_generated": getattr(fetched, "is_generated", None),
    }

    return {"segments": segments, "meta": meta}


async def summarize_chunk_short(cfg: LLMConfig, chunk_text: str) -> str:
    system = (
        "You summarize a short YouTube transcript segment.\n"
        "Rules:\n"
        "- Maximum 35 tokens.\n"
        "- One sentence only.\n"
        "- Describe only the main point.\n"
        "- No explanations."
    )

    return (await chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": chunk_text},
        ],
        model=cfg.model,
        temperature=0.2,
        timeout=25,
    )).strip()


def register_youtube_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def youtube_summarize(url: str) -> dict:
        vid = _extract_video_id(url)
        tr = _fetch_transcript_text(vid)

        cfg = load_llm_config()
        if cfg is None:
            raise LLMNotConfigured("LLM 설정이 없습니다. OPENAI_API_KEY/OPENAI_COMPAT_BASE_URL/OPENAI_MODEL 확인.")

        # 1) 병합(윈도우 확장)
        rough_chunks = merge_segments_by_time(tr["segments"], window_sec=YT_WINDOW_SEC)

        # 2) 의미 있는 청크만
        valid_chunks = [c for c in rough_chunks if is_meaningful_chunk(c["text"])]

        # ✅ 3) 여기서 바로 상한 적용 (비용/시간 절감의 핵심)
        valid_chunks = valid_chunks[:YT_MAX_CHUNKS]

        # 4) 병렬 요약(Map only)
        sem = asyncio.Semaphore(max(1, YT_LLM_PARALLEL))

        async def _summ_one(c: Dict[str, Any]) -> str:
            async with sem:
                return await summarize_chunk_short(cfg, c["text"])

        tasks = [asyncio.create_task(_summ_one(c)) for c in valid_chunks]
        summaries = list(await asyncio.gather(*tasks))

        highlights = [{"start": c["start"], "summary": s} for c, s in zip(valid_chunks, summaries)]

        # ✅ Reduce 제거: 앞단 LLM이 종합하도록 raw highlights 제공
        highlights_md = "\n".join([f"- ({h['start']:.0f}s) {h['summary']}" for h in highlights])

        return {
            "video_id": vid,
            "meta": tr.get("meta", {}),
            "window_sec": YT_WINDOW_SEC,
            "max_chunks": YT_MAX_CHUNKS,
            "parallel": YT_LLM_PARALLEL,
            "highlights": highlights,
            "highlights_md": highlights_md,  # 앞단 LLM 프롬프트에 그대로 붙여 넣기 좋음
        }

# tools/paper.py
from __future__ import annotations

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, List, Tuple

import requests
from pdfminer.high_level import extract_text

import asyncio

from fastmcp import FastMCP
from llm.call import chat, LLMNotConfigured


# -----------------------------
# Cache / limits
# -----------------------------
CACHE_DIR = Path(os.getenv("PAPER_CACHE_DIR", ".cache/papers"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MAX_PDF_MB = int(os.getenv("PAPER_MAX_PDF_MB", "80"))
MAX_PAGES = int(os.getenv("PAPER_MAX_PAGES", "0"))  # 0이면 전체, 아니면 앞 N페이지
PAPER_LLM_PARALLEL = int(os.getenv("PAPER_LLM_PARALLEL", "8"))  # 섹션 요약 동시성 제한


# -----------------------------
# arXiv parsing
# -----------------------------
_ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)
_ARXIV_ID_BARE_RE = re.compile(r"^(?P<id>\d{4}\.\d{4,5}(?:v\d+)?)$", re.IGNORECASE)

def _normalize_arxiv_id(url_or_id: str) -> Optional[str]:
    s = url_or_id.strip()
    s = s.replace(".pdf", "")
    m = _ARXIV_ID_RE.search(s)
    if m:
        return m.group("id")
    m2 = _ARXIV_ID_BARE_RE.search(s)
    if m2:
        return m2.group("id")
    return None

def _to_pdf_url(url_or_id: str) -> str:
    arxiv_id = _normalize_arxiv_id(url_or_id)
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    u = url_or_id.strip()
    if "arxiv.org/pdf/" in u and not u.endswith(".pdf"):
        return u + ".pdf"
    return u

def _fetch_arxiv_meta(arxiv_id: str, timeout: int = 20) -> Dict[str, str]:
    """
    arXiv Atom API: 메타데이터(title/authors/abstract)만.
    """
    try:
        api = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        r = requests.get(api, timeout=timeout, headers={"User-Agent": "mcp-paper-summarizer/1.0"})
        r.raise_for_status()

        # entry title/summary 우선
        entry_title = re.findall(r"<entry>.*?<title>(.*?)</title>", r.text, re.DOTALL)
        entry_summary = re.findall(r"<entry>.*?<summary>(.*?)</summary>", r.text, re.DOTALL)
        paper_title = entry_title[0].strip() if entry_title else ""
        paper_abs = entry_summary[0].strip() if entry_summary else ""

        authors = re.findall(r"<name>(.*?)</name>", r.text)
        authors_str = ", ".join([a.strip() for a in authors]) if authors else ""

        paper_title = re.sub(r"\s+", " ", paper_title)
        paper_abs = re.sub(r"\s+", " ", paper_abs)

        return {
            "arxiv_id": arxiv_id,
            "title": paper_title,
            "abstract": paper_abs,
            "authors": authors_str,
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        }
    except Exception:
        return {
            "arxiv_id": arxiv_id,
            "title": "",
            "abstract": "",
            "authors": "",
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        }


# -----------------------------
# PDF -> text
# -----------------------------
def _download_pdf(pdf_url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(pdf_url, stream=True, timeout=120, headers={"User-Agent": "mcp-paper-summarizer/1.0"}) as r:
        r.raise_for_status()

        cl = r.headers.get("Content-Length")
        if cl is not None:
            size_mb = int(cl) / (1024 * 1024)
            if size_mb > MAX_PDF_MB:
                raise RuntimeError(f"PDF too large: {size_mb:.1f}MB > {MAX_PDF_MB}MB")

        with open(out_path, "wb") as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded > MAX_PDF_MB * 1024 * 1024:
                    raise RuntimeError(f"PDF too large (streaming cap): > {MAX_PDF_MB}MB")

def _clean_text(raw: str) -> str:
    t = raw.replace("\x00", " ")
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)  # hyphen linebreak
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)

    parts = re.split(r"\n\s*(references|bibliography)\s*\n", t, flags=re.IGNORECASE)
    if len(parts) > 1:
        t = parts[0]
    return t.strip()

def _extract_text_from_pdf(pdf_path: Path) -> str:
    if MAX_PAGES and MAX_PAGES > 0:
        raw = extract_text(str(pdf_path), maxpages=MAX_PAGES)
    else:
        raw = extract_text(str(pdf_path))
    return _clean_text(raw)

def _hash_key(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# -----------------------------
# Section splitting (heuristics)
# -----------------------------
_HEADING_PATTERNS = [
    # 1 Introduction / 2 Related Work / 3 Method ...
    r"^\s*(\d+(\.\d+)*)\s+([A-Z][A-Za-z0-9 ,:/\-\(\)]{2,})\s*$",
    # 1. Introduction / 2.1. Preliminaries ...
    r"^\s*(\d+(\.\d+)*\.)\s+([A-Z][A-Za-z0-9 ,:/\-\(\)]{2,})\s*$",
    # ALL CAPS headings
    r"^\s*([A-Z][A-Z0-9 ,:/\-\(\)]{3,})\s*$",
    # common names
    r"^\s*(Abstract|Introduction|Related Work|Background|Preliminaries|Method|Methods|Approach|Model|Architecture|Experiments|Experimental Setup|Results|Discussion|Ablation|Conclusion|Limitations|Future Work|References)\s*$",
]
_REF_SPLIT_RE = re.compile(r"^\s*(References|Bibliography)\s*$", re.IGNORECASE)

def normalize_section_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title).strip()
    return t[:80]

def split_into_sections(text: str) -> List[Tuple[str, str]]:
    lines = text.splitlines()

    # extra safety cut on references
    cut_lines = []
    for ln in lines:
        if _REF_SPLIT_RE.match(ln.strip()):
            break
        cut_lines.append(ln)
    lines = cut_lines

    compiled = [re.compile(p) for p in _HEADING_PATTERNS]

    def is_heading(line: str) -> bool:
        s = line.strip()
        if len(s) < 3 or len(s) > 120:
            return False
        if s.count(".") > 5:
            return False
        for cre in compiled:
            if cre.match(s):
                return True
        return False

    heading_idxs: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        if is_heading(ln):
            heading_idxs.append((i, ln.strip()))

    if len(heading_idxs) < 2:
        return [("Full Text", text)]

    sections: List[Tuple[str, str]] = []
    for k, (idx, title) in enumerate(heading_idxs):
        start = idx + 1
        end = heading_idxs[k + 1][0] if k + 1 < len(heading_idxs) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        sections.append((normalize_section_title(title), body))

    # merge too-short bodies into previous
    merged: List[Tuple[str, str]] = []
    for title, body in sections:
        if not merged:
            merged.append((title, body))
            continue
        if len(body) < 600:
            pt, pb = merged[-1]
            merged[-1] = (pt, (pb + "\n\n" + f"[{title}]\n" + body).strip())
        else:
            merged.append((title, body))
    return merged

def pick_key_sections(sections: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    섹션이 너무 많으면 호출 수가 다시 늘어남.
    핵심 섹션만 선택해서 요약한다.
    """
    keywords = [
        "abstract", "introduction",
        "method", "methods", "approach", "model", "architecture",
        "experiment", "results", "discussion",
        "conclusion", "limitations", "future"
    ]
    picked = []
    for title, body in sections:
        t = title.lower()
        if any(k in t for k in keywords):
            picked.append((title, body))

    if len(picked) < 3:
        picked = sections[:6]

    # 상한: 너무 많으면 길이 큰 순으로 상위 N개
    MAX_SECTIONS = int(os.getenv("PAPER_MAX_SECTIONS", "6"))
    if len(picked) > MAX_SECTIONS:
        picked = sorted(picked, key=lambda x: len(x[1]), reverse=True)[:MAX_SECTIONS]

    return picked


# -----------------------------
# Parallel section summarization (async)
# -----------------------------
async def summarize_sections_parallel(sections: List[Tuple[str, str]]) -> List[Dict[str, str]]:
    sem = asyncio.Semaphore(max(1, PAPER_LLM_PARALLEL))

    async def _one(i: int, title: str, body: str) -> Dict[str, str]:
        prompt = f"""
            너는 논문 섹션 요약가다. 아래는 논문의 한 섹션 본문이다.
            - 섹션의 핵심 주장/아이디어/방법/실험/결과(있으면)를 3~6줄로 요약해라.
            - 불확실하면 '추정' 표기.
            - 과장 금지, 본문에 없는 내용 생성 금지.
            - 군더더기 없이 정보 밀도 높게.
            
            [Section {i+1}/{len(sections)}: {title}]
            {body}
            """.strip()

        async with sem:
            s = await chat(
                [
                    {"role": "system", "content": "You are a precise scientific paper section summarizer."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                timeout=120,
            )
        return {"title": title, "summary": s.strip()}

    tasks = [asyncio.create_task(_one(i, t, b)) for i, (t, b) in enumerate(sections)]
    results = list(await asyncio.gather(*tasks))
    return results


# -----------------------------
# MCP registration
# -----------------------------
def register_paper_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def paper_summarize(url: str) -> Dict[str, str]:
        """
            arXiv 논문(PDF, URL, 또는 논문 ID)을 요약합니다.

            Use when:
            - 사용자가 논문 요약을 요청한 경우
            - arXiv 링크 또는 논문 파일을 제공한 경우
            - 연구 논문의 핵심 내용을 알고 싶어하는 경우

            Tags: summary

            Example:
            - 이 논문 요약해줘 https://arxiv.org/abs/1706.03762
        """
        try:
            pdf_url = _to_pdf_url(url)
            arxiv_id = _normalize_arxiv_id(url) or _normalize_arxiv_id(pdf_url)

            key = arxiv_id if arxiv_id else _hash_key(pdf_url)
            workdir = CACHE_DIR / key
            workdir.mkdir(parents=True, exist_ok=True)

            pdf_path = workdir / "paper.pdf"
            text_path = workdir / "paper.txt"
            meta_path = workdir / "meta.json"

            meta: Dict[str, str] = {}
            if arxiv_id:
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                else:
                    meta = _fetch_arxiv_meta(arxiv_id)
                    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            if not pdf_path.exists():
                _download_pdf(pdf_url, pdf_path)

            if text_path.exists():
                text = text_path.read_text(encoding="utf-8")
            else:
                text = _extract_text_from_pdf(pdf_path)
                text_path.write_text(text, encoding="utf-8")

            if not text or len(text) < 800:
                return {
                    "ok": "false",
                    "message": "PDF 텍스트 추출 결과가 너무 짧습니다(스캔 PDF이거나 추출 실패). ar5iv fallback을 추가하는 것을 권장.",
                }

            sections_all = split_into_sections(text)
            sections_used = pick_key_sections(sections_all)

            # 섹션 요약만 생성(병렬)
            section_summaries = await summarize_sections_parallel(sections_used)

            # 앞단 LLM이 쓰기 좋은 형태 2종 제공
            section_summaries_json = json.dumps(section_summaries, ensure_ascii=False)
            section_summaries_md = "\n\n".join([f"## {x['title']}\n{x['summary']}" for x in section_summaries])

            return {
                "ok": "true",
                "arxiv_id": meta.get("arxiv_id", arxiv_id or ""),
                "title": meta.get("title", ""),
                "authors": meta.get("authors", ""),
                "abstract": meta.get("abstract", ""),
                "pdf_url": meta.get("pdf_url", pdf_url),
                "abs_url": meta.get("abs_url", ""),
                "sections_total": str(len(sections_all)),
                "sections_used": str(len(sections_used)),
                "parallel": str(PAPER_LLM_PARALLEL),
                "section_summaries_json": section_summaries_json,
                "section_summaries_md": section_summaries_md,
            }

        except LLMNotConfigured as e:
            return {"ok": "false", "message": str(e)}
        except Exception as e:
            return {"ok": "false", "message": f"paper_summarize failed: {type(e).__name__}: {e}"}

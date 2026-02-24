# tools/impl/notice_tools.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple, cast
from pydantic import BaseModel, Field

from rapidfuzz import process, fuzz

from agent.tool_registry.registry import register_tool
from app.core.db import db_conn  # db pool context manager


import time


try:
    from app.data.department_data import DEPARTMENT_URL_MAP
except Exception:
    DEPARTMENT_URL_MAP = {}


PAGE_SIZE = 10
FUZZY_SCORE_CUTOFF = 75  # 이 점수 미만이면 매칭 안 함(전체 ko로 fallback)


def _normalize_department(raw: str, default: str = "ko") -> Tuple[str, str, int]:
    raw = (raw or "").strip()
    if not raw:
        return default, default, 100

    dept_codes = set(DEPARTMENT_URL_MAP.values()) | {default}

    # 1) 이미 dept_code로 들어온 경우
    if raw in dept_codes:
        return raw, raw, 100

    # 2) 한글 학과명 정확히 일치
    if raw in DEPARTMENT_URL_MAP:
        return DEPARTMENT_URL_MAP[raw], raw, 100

    # 3) fuzzy
    candidates: List[str] = list(DEPARTMENT_URL_MAP.keys()) + list(dept_codes)

    # 타입체커 경고 회피 (IDE/pyright가 overload를 헷갈려하는 케이스)
    scorer_any = cast(Any, fuzz.WRatio)

    best = process.extractOne(
        query=raw,
        choices=candidates,
        scorer=scorer_any,
        score_cutoff=FUZZY_SCORE_CUTOFF,
    )
    if best is None:
        return default, raw, 0

    matched_text, score, _idx = best
    score = int(score)

    if matched_text in DEPARTMENT_URL_MAP:
        return DEPARTMENT_URL_MAP[matched_text], matched_text, score
    if matched_text in dept_codes:
        return matched_text, matched_text, score

    return default, raw, score


def _safe_table_name(dept_code: str) -> str:
    """
    테이블명 SQL 인젝션 방지용.
    dept_code는 화이트리스트(맵 값들 + ko)로만 허용.
    """
    allowed = set(DEPARTMENT_URL_MAP.values()) | {"ko"}
    if dept_code not in allowed:
        dept_code = "ko"

    # ✅ 여기 접두어를 DB 실제 테이블명에 맞춰 통일
    # 네가 처음 말한 규칙: notice_{학과명/코드}
    return f"notices_{dept_code}"


# -------------------------
# Tool 1: 공지사항 목록(제목만) - 페이지 기반
# -------------------------


class NoticeListArgs(BaseModel):
    department: str = Field("ko", description="학과명(한글) 또는 dept_code. 기본값 전체 공지사항")
    page_start: int = Field(1, ge=1, description="조회 시작 페이지 (1부터)")
    page_end: int = Field(1, ge=1, description="조회 끝 페이지 (page_start 부터)")
    keyword: str = Field("", description="검색 키워드(제목 기준). 기본 ''")


@register_tool(
    name="notice_list",
    description=(
        "대학교 공지사항을 목록으로 조회합니다.\n"
        "- 기본 용도: 사용자가 '공지사항 알려줘/목록/리스트'처럼 목록을 요청할 때 사용.\n"
        "- 반환: article_no, notice_no, title 등 '목록용 기본 메타'만 포함 (상세 내용 없음).\n"
        "- 주의: 사용자가 특정 공지의 '내용/상세/본문'을 명시적으로 요청하지 않았다면 이 도구만 사용하세요"
    ),
    input_model=NoticeListArgs,
    tags=["notice", "read"],
)
async def notice_list(args: NoticeListArgs, ctx: dict) -> dict:
    t0 = time.perf_counter()
    dept_code, matched, score = _normalize_department(args.department, default="ko")
    table = _safe_table_name(dept_code)

    # ✅ page 범위 검증
    if args.page_end < args.page_start:
        return {
            "ok": False,
            "error": "page_end must be greater than or equal to page_start"
        }

    page_count = args.page_end - args.page_start + 1

    # 🔥 과도한 요청 방지 (예: 1~100페이지 이런거 막기)
    if page_count > 2:
        return {
            "ok": False,
            "error": "page range too large (max 5 pages at once)"
        }

    limit = page_count * PAGE_SIZE
    offset = (args.page_start - 1) * PAGE_SIZE

    keyword = (args.keyword or "").strip()
    params: List[Any] = []
    where_sql = ""

    if keyword:
        params.append(f"%{keyword}%")
        where_sql = "WHERE title ILIKE $1"

    offset_param = len(params) + 1
    limit_param = len(params) + 2
    params.extend([offset, limit])

    sql = f"""
    SELECT
        article_no,
        title
    FROM {table}
    {where_sql}
    ORDER BY
        COALESCE(is_pinned, FALSE) DESC,
        pinned_rank NULLS LAST,
        article_no DESC
    OFFSET ${offset_param}
    LIMIT ${limit_param}
    """

    try:
        async with db_conn() as conn:
            rows = await conn.fetch(sql, *params)

        data = [dict(r) for r in rows]
        t1 = time.perf_counter()
        print(f"[notice_list] db_fetch={(t1 - t0) * 1000:.1f}ms rows={len(rows)}")
        return {
            "ok": True,
            "department_code": dept_code,
            "keyword": keyword,
            "data": data,
        }
    except Exception as e:
        print(str(e))
        return {"ok": False, "error": str(e)}


# -------------------------
# Tool 2: 공지사항 상세 - article_no로 1건
# -------------------------
class NoticeDetailArgs(BaseModel):
    department: str = Field("ko", description="학과명(한글) 또는 dept_code. 기본값 전체 공지사항")
    article_no: int = Field(..., ge=1, description="상세 조회할 공지의 article_no")


@register_tool(
    name="notice_detail",
    description=(
        "공지사항 1건을 article_no로 상세 조회합니다.\n"
        "- 사용 조건(필수): 사용자가 특정 공지를 '상세/내용/본문/열어줘'처럼 명시적으로 요청했거나 "
        "article_no를 지정했을 때만 사용.\n"
        "- 반환: contents 및 필요 시 ocr_text 포함.\n"
        "- 제한: 한 번 호출로 1건만 조회합니다. 목록 전체 상세를 한꺼번에 가져오지 마세요.\n"
        "- 권장 흐름: 먼저 notice_list로 목록을 보여주고, 사용자가 선택한 1건에 대해서만 호출하세요."
    ),
    input_model=NoticeDetailArgs,
    tags=["notice", "read"],
)
async def notice_detail(args: NoticeDetailArgs, ctx: dict) -> dict:
    dept_code, matched, score = _normalize_department(args.department, default="ko")
    table = _safe_table_name(dept_code)

    sql = f"""
    SELECT
        url,
        contents,
        ocr_text
    FROM {table}
    WHERE article_no = $1
    LIMIT 1
    """

    try:
        async with db_conn() as conn:
            print(args.article_no)
            row = await conn.fetchrow(sql, args.article_no)

        if row is None:
            print(row)
            return {
                "ok": False,
                "error": "not_found",
                "department_code": dept_code,
                "article_no": args.article_no,
            }
        return {
            "ok": True,
            "department_input": args.department,
            "department_code": dept_code,
            "department_matched": matched,
            "fuzzy_score": score,
            "data": dict(row),
        }
    except Exception as e:
        print(str(e))
        return {"ok": False, "error": str(e), "department_code": dept_code, "article_no": args.article_no}
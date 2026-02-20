# graph/router/llm_fallback.py
from agent.llm.client import get_llm

async def llm_fallback_route(text: str) -> str:
    """
    출력:
      - CALENDAR : "캘린더 작업만" 포함된 요청(등록/조회/수정/삭제 등)이고 다른 도메인 작업이 없음
      - REACT    : DB 조회/요약/기타 도구 사용 등 캘린더 외 작업이 섞이거나 일반 처리
    """
    llm = get_llm()

    prompt = f"""
    다음 사용자 입력을 보고 "카테고리" 하나만 출력하라.
    
    카테고리:
    - CALENDAR: 이 요청을 캘린더 기능(일정 등록/조회/수정/삭제 등)만으로 완전히 처리할 수 있다.
    - REACT: 캘린더 외의 작업(DB 조회/요약/검색/기타 도구 사용)이 포함되거나, 캘린더만으로 끝나지 않는다.
    
    사용자 입력:
    {text}
    
    정답은 반드시 카테고리 이름만 출력하라. (CALENDAR 또는 REACT)
    """.strip()

    resp = await llm.responses.create(
        model="gpt-4o-mini",
        input=prompt,
    )

    result = resp.output_text.strip().upper()
    return result if result in ("CALENDAR", "REACT") else "REACT"
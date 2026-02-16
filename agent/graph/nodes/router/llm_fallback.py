from agent.llm.client import get_llm

async def llm_fallback_route(text: str) -> str:
    llm = get_llm()
    print("llm fallback")
    prompt = f"""
            다음 사용자 입력을 보고
            가장 적절한 카테고리 하나만 선택하라.
            
            카테고리:
            - CHAT: 일반 대화, 설명, 질문
            - CALENDAR: 캘린더 등록,삭제,업데이트 등
            
            사용자 입력:
            {text}
            
            정답은 반드시 카테고리 이름만 출력하라.
            """

    resp = await llm.responses.create(
        model="gpt-4o-mini",
        input=prompt,
    )

    result = resp.output_text.strip().upper()

    return result if result in ("CHAT", "SUMMARY_MCP") else "CHAT"

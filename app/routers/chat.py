from fastapi import APIRouter,Depends
from app.schemas import ChatRequest, ChatResponse
from app.core.security import get_current_user_id  # 너가 만들/이미 있는 함수
router = APIRouter(prefix="/app", tags=["chat"])


def attach_routes(graph_app):
    """
    graph_app: LangGraph compiled app (has .ainvoke)
    """

    @router.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, user_id: int = Depends(get_current_user_id)) -> ChatResponse:
        out = await graph_app.ainvoke(
            {
                "user_text": req.text,
                "mode": req.mode,
                "trace": [],
                "ctx": {"user_id": user_id},  # ✅ 여기서 주입
            }
        )

        return ChatResponse(
            answer=out.get("answer", ""),
            trace=out.get("trace", []),
        )

    return router



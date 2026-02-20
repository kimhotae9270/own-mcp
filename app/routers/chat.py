from fastapi import APIRouter,Depends
from app.schemas import ChatRequest, ChatResponse
from app.core.security import get_current_user_id  # 너가 만들/이미 있는 함수
from app.services.chat_memory import load_mem, save_mem
from app.services.chat_repository import ensure_conversation, append_message
from app.core.db import db_conn

router = APIRouter(prefix="/app", tags=["chat"])

def attach_routes(graph_app):
    """
    graph_app: LangGraph compiled app (has .ainvoke)
    """

    @router.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, user_id: int = Depends(get_current_user_id)) -> ChatResponse:
        # 1) DB: conversation 보장
        async with db_conn() as db:
            conv_uuid = await ensure_conversation(db, user_id=user_id, conversation_id=req.conversation_id)

            # 2) Redis: 숏텀 메모리 로드
            mem = await load_mem(user_id, req.conversation_id)

            # 3) DB append: user 메시지 저장
            await append_message(db, user_id=user_id, conversation_id=conv_uuid, role="user", content=req.text)

            # 4) graph invoke (memory 주입)
            out = await graph_app.ainvoke({
                "user_text": req.text,
                "mode": req.mode,
                "trace": [],
                "ctx": {
                    "user_id": user_id,
                    "memory": mem,
                },
            })

            answer = out.get("answer", "")
            trace = out.get("trace", [])

            # 5) DB append: assistant 메시지 저장
            await append_message(db, user_id=user_id, conversation_id=conv_uuid, role="assistant", content=answer,
                                 trace=trace)

        # 6) Redis 업데이트 (graph가 summary/state를 주면 같이 저장)
        await save_mem(
            user_id, req.conversation_id,
            user_text=req.text,
            assistant_text=answer,
            summary=out.get("summary"),
            state=out.get("state"),
        )

        return ChatResponse(answer=answer, trace=trace)
    return router


from fastapi import APIRouter
from api.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


def attach_routes(graph_app):
    """
    graph_app: LangGraph compiled app (has .ainvoke)
    """
    @router.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        out = await graph_app.ainvoke(
            {
                "user_text": req.text,
                "mode": req.mode,
                "trace": [],
            }
        )

        return ChatResponse(
            answer=out.get("answer", ""),
            trace=out.get("trace", []),
        )

    return router
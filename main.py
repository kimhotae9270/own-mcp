from dotenv import load_dotenv
load_dotenv()  # .env 로드
from fastapi import FastAPI
from app.routers.chat import attach_routes

from app.routers.auth import router as auth_router


# 여기만 나중에 바뀝니다:
# - 지금은 graph_app import
# - 나중에는 DI/팩토리로 교체 가능
from agent.graph.build import graph_app  # 너의 LangGraph compile 결과
from agent.embedding.loader import load_mcp_embeddings
load_mcp_embeddings()
app = FastAPI(title="MCP Agent API")
app.include_router(auth_router)
app.include_router(attach_routes(graph_app))

from fastapi import FastAPI
from api.routes import attach_routes
from dotenv import load_dotenv
load_dotenv()  # .env 로드
# 여기만 나중에 바뀝니다:
# - 지금은 graph_app import
# - 나중에는 DI/팩토리로 교체 가능
from mcp_app.graph.build import graph_app  # 너의 LangGraph compile 결과
from mcp_app.graph.embedding.loader import load_mcp_embeddings
load_mcp_embeddings()
app = FastAPI(title="MCP Agent API")

app.include_router(attach_routes(graph_app))
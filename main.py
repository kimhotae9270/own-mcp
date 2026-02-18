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
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.db import init_db_pool, close_db_pool
from app.core.scheduler import start_scheduler, shutdown_scheduler
from app.core.redis_client import r
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🔥 Startup 영역
    await init_db_pool()          # DB pool 생성
    scheduler = start_scheduler()  # 기존 스케줄러 시작

    # (선택) Redis 연결 체크
    try:
        await r.ping()
        print("✅ Redis connected")
    except Exception as e:
        print("❌ Redis connection failed:", e)
        raise

    try:
        yield
    finally:
        # 🔥 Shutdown 영역
        shutdown_scheduler(scheduler)
        await close_db_pool()     # DB pool 종료
        await r.close()  # Redis 연결 종료

load_mcp_embeddings()
app = FastAPI(title="MCP Agent API",lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(attach_routes(graph_app))

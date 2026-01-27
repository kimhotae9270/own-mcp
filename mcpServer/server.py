# server.py
from dotenv import load_dotenv
load_dotenv()  # .env 로드
from fastmcp import FastMCP
from tools import register_all_tools

mcp = FastMCP(name="KB-Ingest-Summarizer")

# 모든 tool 모듈을 여기서 한 번에 등록
register_all_tools(mcp)

if __name__ == "__main__":
    # FastMCP 표준 실행
    mcp.run(
        transport="http",
        host="127.0.0.1",
        port=8000,
        path="/"
    )
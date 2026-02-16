from openai import AsyncOpenAI
import os

_client = None

def get_llm():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
    return _client

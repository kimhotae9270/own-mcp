from openai import OpenAI
from .config import EMBEDDING_MODEL

client = OpenAI()

def embed(text: str) -> list[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding

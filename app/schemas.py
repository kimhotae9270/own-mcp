from typing import Literal, Optional, List
from pydantic import BaseModel, Field


Mode = Literal["AUTO", "CHAT", "CALENDAR"]


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, description="User message")
    mode: Mode = Field("AUTO", description="Routing mode")


class ChatResponse(BaseModel):
    answer: str
    trace: List[str] = []

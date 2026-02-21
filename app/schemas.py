from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

Mode = Literal["AUTO", "CHAT", "CALENDAR"]


class ChatRequest(BaseModel):
    text: str = Field(..., max_length=50)   # ✅ 서버에서도 50자 강제
    mode: str | None = None
    conversation_id: str  # UUID 문자열(프론트가 보내줌)


class ChatResponse(BaseModel):
    answer: str
    trace: List[str] = []

class ConversationItem(BaseModel):
    id: str
    title: Optional[str] = None
    last_active_at: datetime

class MessageItem(BaseModel):
    role: str
    content: str
    created_at: datetime

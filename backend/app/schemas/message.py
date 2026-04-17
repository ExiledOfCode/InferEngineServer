from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict, Literal, Optional

class MessageCreate(BaseModel):
    content: str
    think_enabled: bool = True

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    reasoning_content: Optional[str] = None
    raw_content: Optional[str] = None
    inference_trace: Optional[Dict[str, Any]] = None
    feedback: Optional[Literal["like", "dislike"]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageWithTraceResponse(MessageResponse):
    inference_trace: Optional[Dict[str, Any]] = None


class MessageFeedbackUpdate(BaseModel):
    feedback: Optional[Literal["like", "dislike"]] = None

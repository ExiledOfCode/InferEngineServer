from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict, Optional

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageWithTraceResponse(MessageResponse):
    inference_trace: Optional[Dict[str, Any]] = None

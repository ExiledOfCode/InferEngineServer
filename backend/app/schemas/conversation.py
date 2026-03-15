from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ConversationCreate(BaseModel):
    title: Optional[str] = "新对话"

class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

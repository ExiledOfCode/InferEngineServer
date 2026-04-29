"""文件说明：Pydantic 数据结构定义，约束 conversation 相关接口的请求和响应格式。"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ConversationCreate(BaseModel):
    title: Optional[str] = "新对话"

class ConversationUpdate(BaseModel):
    title: Optional[str] = None

class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

"""文件说明：Pydantic 数据结构定义，约束 user 相关接口的请求和响应格式。"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    status: Optional[str] = None
    password: Optional[str] = None

class UserResponse(UserBase):
    id: int
    role: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

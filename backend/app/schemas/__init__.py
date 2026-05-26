"""文件说明：Pydantic schema 包入口，集中导出接口请求和响应模型。"""

from .user import UserCreate, UserUpdate, UserResponse, UserLogin, UserRegister, Token
from .conversation import ConversationCreate, ConversationResponse, ConversationUpdate
from .message import MessageCreate, MessageResponse
from .inference import (
    InferenceEngineOptionResponse,
    InferenceEngineOptionsResponse,
    InferenceEngineOptionsUpdateRequest,
    InferenceModelSelectRequest,
)

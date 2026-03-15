from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "ai_chat"
    
    # JWT配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24小时
    
    # 推理引擎配置
    INFERENCE_ENGINE_PATH: str = "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama"
    # 可选：指定模型目录（绝对路径，或相对 INFERENCE_ENGINE_PATH/models 的目录名）
    INFERENCE_MODEL_DIR: str = "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2.5-1.5B-Instruct"
    # INFERENCE_MODEL_DIR: str = "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2.5-0.5B"
    # 可选：指定模型文件（绝对路径，或相对 INFERENCE_ENGINE_PATH/models 的路径）
    INFERENCE_MODEL_PATH: str = ""
    # 可选：指定 tokenizer 文件（绝对路径，或相对 INFERENCE_ENGINE_PATH/models 的路径）
    INFERENCE_TOKENIZER_PATH: str = ""

    # CORS 配置（逗号分隔）
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://0.0.0.0:5173"
    # 可选：正则匹配 Origin（适合本地开发多端口场景）
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+)(:\d+)?$"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def CORS_ORIGINS(self) -> list[str]:
        origins = [item.strip() for item in self.CORS_ALLOW_ORIGINS.split(",") if item.strip()]
        return origins

    @property
    def CORS_ORIGIN_REGEX(self) -> Optional[str]:
        value = self.CORS_ALLOW_ORIGIN_REGEX.strip()
        return value or None
    
    class Config:
        env_file = ".env"

settings = Settings()

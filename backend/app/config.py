import json
from typing import Any, Optional

from pydantic_settings import BaseSettings

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
    INFERENCE_ENGINE_PATH: str = "/home/wjy/workspace/MyInferEngine/KuiperLLama"
    # 可选：指定模型目录（绝对路径，或相对 INFERENCE_ENGINE_PATH/models 的目录名）
    INFERENCE_MODEL_DIR: str = ""
    # 可选：指定模型文件（绝对路径，或相对 INFERENCE_ENGINE_PATH/models 的路径）
    INFERENCE_MODEL_PATH: str = ""
    # 可选：指定 tokenizer 文件（绝对路径，或相对 INFERENCE_ENGINE_PATH/models 的路径）
    INFERENCE_TOKENIZER_PATH: str = ""
    # 可选：JSON 数组，显式声明可供前端切换的模型列表；为空时使用下面的默认双模型目录
    INFERENCE_MODEL_SPECS_JSON: str = ""

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

    @property
    def DEFAULT_INFERENCE_MODEL_SPECS(self) -> list[dict[str, str]]:
        engine_path = self.INFERENCE_ENGINE_PATH.rstrip("/")
        return [
            {
                "id": "qwen2_5_0_5b",
                "name": "Qwen2.5-0.5B",
                "family": "qwen2",
                "dir": f"{engine_path}/models/Qwen2.5-0.5B",
                "model_path": f"{engine_path}/models/Qwen2.5-0.5B/Qwen2.5-0.5B.bin",
                "tokenizer_path": f"{engine_path}/models/Qwen2.5-0.5B/tokenizer.json",
                "executable_path": f"{engine_path}/build_qwen2/demo/qwen_infer",
            },
            {
                "id": "qwen3_4b",
                "name": "Qwen3-4B",
                "family": "qwen3",
                "dir": f"{engine_path}/models/Qwen3-4B",
                "model_path": f"{engine_path}/models/Qwen3-4B/Qwen3-4B.bin",
                "tokenizer_path": f"{engine_path}/models/Qwen3-4B/tokenizer.json",
                "executable_path": f"{engine_path}/build_qwen3/demo/qwen3_infer",
            },
        ]

    @property
    def INFERENCE_MODEL_SPECS(self) -> list[dict[str, Any]]:
        raw = self.INFERENCE_MODEL_SPECS_JSON.strip()
        if not raw:
            return self.DEFAULT_INFERENCE_MODEL_SPECS

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self.DEFAULT_INFERENCE_MODEL_SPECS

        if not isinstance(data, list):
            return self.DEFAULT_INFERENCE_MODEL_SPECS

        specs: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            normalized = {str(key): value for key, value in item.items()}
            if normalized:
                specs.append(normalized)
        return specs or self.DEFAULT_INFERENCE_MODEL_SPECS
    
    class Config:
        env_file = ".env"
        # Allow additional env vars (e.g. INFERENCE_MAX_NEW_TOKENS) that are
        # consumed elsewhere via os.getenv, without failing settings init.
        extra = "ignore"

settings = Settings()

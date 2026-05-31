"""文件说明：后端配置中心，从环境变量和默认配置生成数据库、鉴权与推理引擎参数。"""

import json
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

from .config_defaults import (
    DEFAULT_INFERENCE_ENGINE_OPTIONS,
    DEFAULT_INFERENCE_MODELS,
    DEFAULT_INFERENCE_OPERATOR_OPTIONS,
)


def _dump_default_json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


class Settings(BaseSettings):
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "ai_chat"
    SQL_ECHO: bool = False

    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # 推理引擎配置
    INFERENCE_ENGINE_PATH: str = str(Path(__file__).resolve().parents[3] / "W_InferEngine")
    INFERENCE_MODEL_DIR: str = "~/models/Qwen2.5-1.5B-Instruct"
    INFERENCE_MODEL_PATH: str = ""
    INFERENCE_TOKENIZER_PATH: str = ""
    INFERENCE_DEFAULT_MODEL_ID: str = "qwen2_5_1_5b_instruct"
    INFERENCE_TEMPERATURE: float = 0.0
    INFERENCE_RUNTIME_OPTIONS_PATH: str = "runtime/inference_options.json"
    INFERENCE_ENGINE_OPTIONS_JSON: str = _dump_default_json(DEFAULT_INFERENCE_ENGINE_OPTIONS)
    INFERENCE_OPERATOR_OPTIONS_PATH: str = "runtime/operator_options.json"
    INFERENCE_OPERATOR_OPTIONS_JSON: str = _dump_default_json(DEFAULT_INFERENCE_OPERATOR_OPTIONS)
    INFERENCE_MODELS_JSON: str = _dump_default_json(DEFAULT_INFERENCE_MODELS)

    # CORS 配置
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://0.0.0.0:5173"
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+)(:\d+)?$"

    # 默认压制前端轮询接口的 access log
    SUPPRESSED_ACCESS_LOG_PATHS: str = "/api/inference/status"

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return [item.strip() for item in self.CORS_ALLOW_ORIGINS.split(",") if item.strip()]

    @property
    def CORS_ORIGIN_REGEX(self) -> Optional[str]:
        value = self.CORS_ALLOW_ORIGIN_REGEX.strip()
        return value or None

    @property
    def ACCESS_LOG_SUPPRESSED_PATHS(self) -> set[str]:
        return {
            item.strip()
            for item in self.SUPPRESSED_ACCESS_LOG_PATHS.split(",")
            if item.strip()
        }

    class Config:
        env_file = ".env"


settings = Settings()

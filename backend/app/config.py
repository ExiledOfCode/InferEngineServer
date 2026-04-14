from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "ai_chat"
    SQL_ECHO: bool = False
    
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
    # 可选：默认模型 ID。配合 INFERENCE_MODELS_JSON 使用。
    INFERENCE_DEFAULT_MODEL_ID: str = "qwen2_5_1_5b_instruct"
    # 可选：运行时优化开关持久化文件。相对路径按 backend 目录解析。
    INFERENCE_RUNTIME_OPTIONS_PATH: str = "runtime/inference_options.json"
    # 可选：引擎优化项默认配置。支持后续继续扩展新选项。
    INFERENCE_ENGINE_OPTIONS_JSON: str = """
[
  {
    "id": "trace_enabled",
    "name": "数据埋点",
    "description": "控制引擎阶段埋点与算子 profiling，关闭后更接近纯推理速度。",
    "default_enabled": true,
    "requires_restart": true
  },
  {
    "id": "warmup_on_model_switch",
    "name": "切模预热",
    "description": "切换模型后立即启动常驻进程，减少首条请求的冷启动等待。",
    "default_enabled": true,
    "requires_restart": false
  }
]
"""
    # 可选：多模型配置，JSON 数组或 {"models": [...]}。
    INFERENCE_MODELS_JSON: str = """
[
  {
    "id": "qwen2_5_1_5b_instruct",
    "name": "Qwen2.5-1.5B-Instruct",
    "family": "qwen2",
    "model_dir": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2.5-1.5B-Instruct",
    "model_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2.5-1.5B-Instruct/Qwen2.5-1.5B-Instruct.bin",
    "tokenizer_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2.5-1.5B-Instruct/tokenizer.json",
    "executable_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/build/demo/qwen_infer",
    "prompt_format": "chatml"
  },
  {
    "id": "qwen3_1_7b",
    "name": "Qwen3-1.7B",
    "family": "qwen3",
    "model_dir": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen3-1.7B",
    "model_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen3-1.7B/Qwen3-1.7B.bin",
    "tokenizer_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen3-1.7B/tokenizer.json",
    "executable_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/build/demo/qwen3_infer",
    "prompt_format": "chatml",
    "max_new_tokens": 256
  },
  {
    "id": "qwen3_0_6b",
    "name": "Qwen3-0.6B",
    "family": "qwen3",
    "model_dir": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen3-0.6B",
    "model_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen3-0.6B/Qwen3-0.6B.bin",
    "tokenizer_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen3-0.6B/tokenizer.json",
    "executable_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/build/demo/qwen3_infer",
    "prompt_format": "chatml",
    "max_new_tokens": 256
  },
  {
    "id": "qwen2_0_5b",
    "name": "Qwen2-0.5B",
    "family": "qwen2",
    "model_dir": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2-0.5B",
    "model_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2-0.5B/Qwen2-0.5B.bin",
    "tokenizer_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/models/Qwen2-0.5B/tokenizer.json",
    "executable_path": "/mnt/d/Project_Repository/Open_Source_Projects/MyInferenceEngine/KuiperLLama/build/demo/qwen_infer",
    "prompt_format": "chatml"
  }
]
"""

    # CORS 配置（逗号分隔）
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://0.0.0.0:5173"
    # 可选：正则匹配 Origin（适合本地开发多端口场景）
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+)(:\d+)?$"
    # 默认压制前端轮询接口的 access log，避免掩盖真正的异常信息
    SUPPRESSED_ACCESS_LOG_PATHS: str = "/api/inference/status"
    
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
    def ACCESS_LOG_SUPPRESSED_PATHS(self) -> set[str]:
        return {
            item.strip()
            for item in self.SUPPRESSED_ACCESS_LOG_PATHS.split(",")
            if item.strip()
        }
    
    class Config:
        env_file = ".env"

settings = Settings()

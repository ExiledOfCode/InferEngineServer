import os
import queue
import subprocess
import threading
from typing import Any, Dict, List, Optional

from ...config import settings
from ...config_defaults import DEFAULT_INFERENCE_ENGINE_OPTIONS, DEFAULT_INFERENCE_OPERATOR_OPTIONS
from .errors import InferenceCancelledError
from .models import ModelRegistryMixin
from .operators import OperatorOptionsMixin
from .process import ProcessMixin
from .prompts import PromptMixin
from .runtime import RuntimeOptionsMixin
from .trace import TraceMixin


class InferenceService(
    RuntimeOptionsMixin,
    OperatorOptionsMixin,
    PromptMixin,
    TraceMixin,
    ModelRegistryMixin,
    ProcessMixin,
):
    """基于 KuiperLLama demo 可执行文件的推理服务。"""

    THINK_OPEN_TAG = "<think>"
    THINK_CLOSE_TAG = "</think>"
    THINK_NO_ANSWER_FALLBACK = "（当前 max_token 已耗尽，仅生成了思考过程，请提高 max_token 后重试。）"
    MIN_MAX_NEW_TOKENS = 16
    MAX_MAX_NEW_TOKENS = None
    MODEL_FILE_MAGIC = 0x4B4D444C
    MIN_TEMPERATURE = 0.0
    MAX_TEMPERATURE = 2.0

    DEFAULT_ENGINE_OPTIONS: List[Dict[str, Any]] = DEFAULT_INFERENCE_ENGINE_OPTIONS
    DEFAULT_OPERATOR_OPTIONS: List[Dict[str, Any]] = DEFAULT_INFERENCE_OPERATOR_OPTIONS

    def __init__(self):
        self.engine_path = os.path.abspath(settings.INFERENCE_ENGINE_PATH)
        self.models_root = os.path.join(self.engine_path, "models")

        self.executable: Optional[str] = None
        self.model_path: Optional[str] = None
        self.tokenizer_path: Optional[str] = None
        self.tokenizer_type: Optional[str] = None
        self.model_selection_source: str = "none"
        self.current_model_id: Optional[str] = None
        self.current_model_name: Optional[str] = None
        self.current_model_family: Optional[str] = None
        self.current_model_supports_reasoning: bool = False
        self.current_model_dir: Optional[str] = None
        self.current_model_seq_len: Optional[int] = None
        self.available_models: List[Dict[str, Any]] = []

        self.process: Optional[subprocess.Popen] = None
        self.stdout_queue: Optional[queue.Queue] = None
        self.stdout_reader: Optional[threading.Thread] = None

        self.lock = threading.Lock()
        self.stdin_lock = threading.Lock()
        self.counter_lock = threading.Lock()
        self.trace_lock = threading.Lock()
        self.request_state_lock = threading.Lock()
        self.request_counter = 0
        self.active_request_id: Optional[int] = None
        self.cancel_requested = False
        self.engine_starting = False
        self.current_trace: Optional[Dict[str, Any]] = None
        self.last_trace: Optional[Dict[str, Any]] = None

        legacy_max_steps = self._read_optional_positive_int("INFERENCE_MAX_STEPS")
        default_max_new_tokens = legacy_max_steps if legacy_max_steps is not None else 128
        self.default_max_new_tokens = self._read_positive_int("INFERENCE_MAX_NEW_TOKENS", default_max_new_tokens)
        self.max_new_tokens = self.default_max_new_tokens
        self.default_temperature = self._read_float("INFERENCE_TEMPERATURE", 0.0)
        self.temperature = self.default_temperature

        self.timeout_seconds = self._read_positive_int("INFERENCE_TIMEOUT_SECONDS", 600)
        self.startup_timeout_seconds = self._read_positive_int("INFERENCE_STARTUP_TIMEOUT_SECONDS", 900)
        self.max_history_messages = self._read_positive_int("INFERENCE_MAX_HISTORY_MESSAGES", 8)
        self.max_prompt_chars = self._read_positive_int("INFERENCE_MAX_PROMPT_CHARS", 2400)

        self.default_prompt_format = self._read_prompt_format("INFERENCE_PROMPT_FORMAT", "auto")
        self.prompt_format = self.default_prompt_format
        self.default_raw_with_history = self._read_bool("INFERENCE_RAW_WITH_HISTORY", False)
        self.raw_with_history = self.default_raw_with_history
        self.default_system_prompt = (
            os.getenv(
                "INFERENCE_SYSTEM_PROMPT",
                "你是一个乐于助人的中文 AI 助手。请用简洁、自然的中文回答。"
            ).strip()
            or "你是一个乐于助人的中文 AI 助手。请用简洁、自然的中文回答。"
        )
        self.system_prompt = self.default_system_prompt

        self.eager_start = self._read_bool("INFERENCE_EAGER_START", False)
        self.default_model_id = str(getattr(settings, "INFERENCE_DEFAULT_MODEL_ID", "") or "").strip()
        self.runtime_options_path = self._resolve_runtime_options_path()
        self.runtime_state_payload = self._load_runtime_payload()
        self.engine_option_catalog = self._load_engine_option_catalog()
        self.engine_option_values = self._load_engine_option_values(self.runtime_state_payload)
        self.operator_options_path = self._resolve_operator_options_path()
        self.operator_state_payload = self._load_operator_payload()
        self.operator_group_catalog = self._load_operator_group_catalog()
        self.operator_option_values = self._load_operator_option_values(self.operator_state_payload)
        self.runtime_max_new_tokens = self._load_runtime_max_new_tokens(self.runtime_state_payload)
        self.runtime_temperature = self._load_runtime_temperature(self.runtime_state_payload)
        self.trace_enabled = False
        self.optimized_weight_loading = False
        self.paged_kv_cache = True
        self.warmup_on_model_switch = True
        self._apply_engine_options(initializing=True)
        self.max_new_tokens = self._resolved_max_new_tokens(None)
        self.temperature = self._resolved_temperature(None)

        if self.max_new_tokens < 8:
            print(f"[WARN] INFERENCE_MAX_NEW_TOKENS={self.max_new_tokens} 偏小，可能导致回复很短。")

        self._load_model_registry()
        if self.eager_start:
            self._start_engine()
        else:
            print("[Inference] 已启用延迟启动：首次 generate 时再启动推理进程。")

    def debug_status(self) -> Dict[str, object]:
        return {
            "ready": self.is_ready(),
            "running": self.is_running(),
            "active_request_id": self.active_request_id,
            "cancel_requested": self.cancel_requested,
            "engine_path": self.engine_path,
            "executable": self.executable,
            "model_selection_source": self.model_selection_source,
            "current_model_id": self.current_model_id,
            "current_model_name": self.current_model_name,
            "current_model_family": self.current_model_family,
            "current_model_supports_reasoning": self.current_model_supports_reasoning,
            "current_model_dir": self.current_model_dir,
            "current_model_seq_len": self.current_model_seq_len,
            "model_path": self.model_path,
            "tokenizer_path": self.tokenizer_path,
            "tokenizer_type": self.tokenizer_type,
            "available_models": self.list_models(),
            "configured_model_dir": settings.INFERENCE_MODEL_DIR,
            "configured_model_path": settings.INFERENCE_MODEL_PATH,
            "configured_tokenizer_path": settings.INFERENCE_TOKENIZER_PATH,
            "configured_default_model_id": getattr(settings, "INFERENCE_DEFAULT_MODEL_ID", ""),
            "has_models_json": bool(str(getattr(settings, "INFERENCE_MODELS_JSON", "") or "").strip()),
            "runtime_options_path": self.runtime_options_path,
            "operator_options_path": self.operator_options_path,
            "engine_options": self.list_engine_options(),
            "operator_options": self.list_operator_groups(),
            "operator_env": self.operator_process_env(),
            "trace_enabled": self.trace_enabled,
            "optimized_weight_loading": self.optimized_weight_loading,
            "effective_optimized_weight_loading": self.optimized_weight_loading and self._supports_optimized_weight_loading(),
            "paged_kv_cache": self.paged_kv_cache,
            "effective_paged_kv_cache": self.paged_kv_cache and self._supports_paged_kv_cache(),
            "warmup_on_model_switch": self.warmup_on_model_switch,
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "prompt_format": self.prompt_format,
            "effective_prompt_format": self._effective_prompt_format(),
            "system_prompt": self.system_prompt,
            "raw_with_history": self.raw_with_history,
            "max_history_messages": self.max_history_messages,
            "max_prompt_chars": self.max_prompt_chars,
            "timeout_seconds": self.timeout_seconds,
            "startup_timeout_seconds": self.startup_timeout_seconds,
            "eager_start": self.eager_start,
            "pid": self.process.pid if self.process and self.is_running() else None,
            "trace_state": self.trace_status().get("state", "idle"),
        }

    def _mock_response(self, prompt: str) -> str:
        executable_name = os.path.basename(self.executable) if self.executable else self._default_executable_name(
            self.current_model_family or "qwen2"
        )
        return f"""推理引擎未就绪。

当前模型: {self.current_model_name or '未选择'} ({self.current_model_id or '-'})
你的问题是: {prompt}

请检查:
- 可执行文件({executable_name}): {'✓' if self.executable and os.path.exists(self.executable) else '❌ 未找到'}
- 模型文件(.bin): {'✓' if self.model_path and os.path.exists(self.model_path) else '❌ 未找到'}
- 分词器(tokenizer.json): {'✓' if self.tokenizer_path and os.path.exists(self.tokenizer_path) else '❌ 未找到'}
"""

    def clear_history(self):
        return None

    def shutdown(self):
        self._stop_process()


inference_service = InferenceService()

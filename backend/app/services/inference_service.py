import json
import os
import queue
import subprocess
import threading
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..config import settings


class InferenceCancelledError(Exception):
    pass


class InferenceService:
    """基于 KuiperLLama demo 可执行文件的推理服务。"""

    THINK_OPEN_TAG = "<think>"
    THINK_CLOSE_TAG = "</think>"
    THINK_NO_ANSWER_FALLBACK = "（当前 max_token 已耗尽，仅生成了思考过程，请提高 max_token 后重试。）"
    MIN_MAX_NEW_TOKENS = 16
    MAX_MAX_NEW_TOKENS = 2048

    DEFAULT_ENGINE_OPTIONS: List[Dict[str, Any]] = [
        {
            "id": "trace_enabled",
            "name": "数据埋点",
            "description": "控制引擎阶段埋点与算子 profiling，关闭后更接近纯推理速度。",
            "default_enabled": True,
            "requires_restart": True,
        },
        {
            "id": "warmup_on_model_switch",
            "name": "切模预热",
            "description": "切换模型后立即启动常驻进程，减少首条请求的冷启动等待。",
            "default_enabled": True,
            "requires_restart": False,
        },
    ]

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
        self.current_model_dir: Optional[str] = None
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
        self.current_trace: Optional[Dict[str, Any]] = None
        self.last_trace: Optional[Dict[str, Any]] = None

        legacy_max_steps = self._read_optional_positive_int("INFERENCE_MAX_STEPS")
        default_max_new_tokens = legacy_max_steps if legacy_max_steps is not None else 128
        self.default_max_new_tokens = self._read_positive_int("INFERENCE_MAX_NEW_TOKENS", default_max_new_tokens)
        self.max_new_tokens = self.default_max_new_tokens

        self.timeout_seconds = self._read_positive_int("INFERENCE_TIMEOUT_SECONDS", 180)
        self.startup_timeout_seconds = self._read_positive_int("INFERENCE_STARTUP_TIMEOUT_SECONDS", 900)
        self.max_history_messages = self._read_positive_int("INFERENCE_MAX_HISTORY_MESSAGES", 8)
        self.max_prompt_chars = self._read_positive_int("INFERENCE_MAX_PROMPT_CHARS", 2400)

        self.default_prompt_format = self._read_prompt_format("INFERENCE_PROMPT_FORMAT", "auto")
        self.prompt_format = self.default_prompt_format
        self.default_raw_with_history = self._read_bool("INFERENCE_RAW_WITH_HISTORY", False)
        self.raw_with_history = self.default_raw_with_history
        self.default_system_prompt = (
            os.getenv("INFERENCE_SYSTEM_PROMPT", "You are a helpful assistant.").strip()
            or "You are a helpful assistant."
        )
        self.system_prompt = self.default_system_prompt

        self.eager_start = self._read_bool("INFERENCE_EAGER_START", False)
        self.default_model_id = str(getattr(settings, "INFERENCE_DEFAULT_MODEL_ID", "") or "").strip()
        self.runtime_options_path = self._resolve_runtime_options_path()
        self.runtime_state_payload = self._load_runtime_payload()
        self.engine_option_catalog = self._load_engine_option_catalog()
        self.engine_option_values = self._load_engine_option_values(self.runtime_state_payload)
        self.runtime_max_new_tokens = self._load_runtime_max_new_tokens(self.runtime_state_payload)
        self.trace_enabled = True
        self.warmup_on_model_switch = True
        self._apply_engine_options(initializing=True)
        self.max_new_tokens = self._resolved_max_new_tokens(None)

        if self.max_new_tokens < 8:
            print(f"[WARN] INFERENCE_MAX_NEW_TOKENS={self.max_new_tokens} 偏小，可能导致回复很短。")

        self._load_model_registry()
        if self.eager_start:
            self._start_engine()
        else:
            print("[Inference] 已启用延迟启动：首次 generate 时再启动推理进程。")

    @staticmethod
    def _read_positive_int(env_name: str, default: int) -> int:
        raw = os.getenv(env_name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return value if value > 0 else default

    @staticmethod
    def _read_optional_positive_int(env_name: str) -> Optional[int]:
        raw = os.getenv(env_name)
        if raw is None:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if value > 0 else None

    @staticmethod
    def _read_bool(env_name: str, default: bool) -> bool:
        raw = os.getenv(env_name)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _read_prompt_format(env_name: str, default: str) -> str:
        raw = str(os.getenv(env_name, default)).strip().lower()
        return raw if raw in {"raw", "chatml", "auto"} else default

    @staticmethod
    def _coerce_positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _normalize_model_id(value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "default"
        normalized = []
        for ch in raw:
            normalized.append(ch if ch.isalnum() else "_")
        result = "".join(normalized).strip("_")
        while "__" in result:
            result = result.replace("__", "_")
        return result or "default"

    def _resolve_runtime_options_path(self) -> str:
        configured = str(getattr(settings, "INFERENCE_RUNTIME_OPTIONS_PATH", "") or "").strip()
        if configured:
            if os.path.isabs(configured):
                return os.path.abspath(configured)
            backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            return os.path.abspath(os.path.join(backend_root, configured))
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(backend_root, "runtime", "inference_options.json")

    def _load_runtime_payload(self) -> Dict[str, Any]:
        path = self.runtime_options_path
        if not path or not os.path.exists(path):
            return {}

        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            print(f"[Inference] 运行时配置读取失败: {exc}")
            return {}

        return payload if isinstance(payload, dict) else {}

    def _parse_engine_options_config(self) -> List[Dict[str, Any]]:
        raw = str(getattr(settings, "INFERENCE_ENGINE_OPTIONS_JSON", "") or "").strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except Exception as exc:
            print(f"[Inference] INFERENCE_ENGINE_OPTIONS_JSON 解析失败: {exc}")
            return []

        if isinstance(payload, dict):
            items = payload.get("options", [])
        elif isinstance(payload, list):
            items = payload
        else:
            return []

        results = []
        for item in items:
            if isinstance(item, dict):
                results.append(item)
        return results

    def _load_engine_option_catalog(self) -> List[Dict[str, Any]]:
        order: List[str] = []
        catalog: Dict[str, Dict[str, Any]] = {}

        for item in self.DEFAULT_ENGINE_OPTIONS:
            option_id = self._normalize_model_id(item.get("id"))
            order.append(option_id)
            catalog[option_id] = {
                "id": option_id,
                "name": str(item.get("name") or option_id),
                "description": str(item.get("description") or "").strip(),
                "default_enabled": self._coerce_bool(item.get("default_enabled"), False),
                "requires_restart": self._coerce_bool(item.get("requires_restart"), False),
            }

        for raw_item in self._parse_engine_options_config():
            option_id = self._normalize_model_id(raw_item.get("id"))
            if not option_id:
                continue
            if option_id not in catalog:
                order.append(option_id)
                catalog[option_id] = {
                    "id": option_id,
                    "name": option_id,
                    "description": "",
                    "default_enabled": False,
                    "requires_restart": False,
                }

            catalog[option_id]["name"] = str(raw_item.get("name") or catalog[option_id]["name"]).strip() or option_id
            catalog[option_id]["description"] = str(
                raw_item.get("description") or catalog[option_id]["description"]
            ).strip()
            if "default_enabled" in raw_item:
                catalog[option_id]["default_enabled"] = self._coerce_bool(
                    raw_item.get("default_enabled"), catalog[option_id]["default_enabled"]
                )
            if "requires_restart" in raw_item:
                catalog[option_id]["requires_restart"] = self._coerce_bool(
                    raw_item.get("requires_restart"), catalog[option_id]["requires_restart"]
                )

        return [catalog[option_id] for option_id in order]

    @classmethod
    def _clamp_max_new_tokens(cls, value: Any, default: int) -> int:
        parsed = cls._coerce_positive_int(value, default)
        return max(cls.MIN_MAX_NEW_TOKENS, min(cls.MAX_MAX_NEW_TOKENS, parsed))

    def _load_engine_option_values(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
        values = {
            item["id"]: self._coerce_bool(item.get("default_enabled"), False)
            for item in self.engine_option_catalog
        }

        payload = payload or {}

        raw_options: Dict[str, Any] = {}
        if isinstance(payload, dict) and isinstance(payload.get("options"), dict):
            raw_options = payload["options"]

        for raw_id, raw_value in raw_options.items():
            option_id = self._normalize_model_id(raw_id)
            if option_id in values:
                values[option_id] = self._coerce_bool(raw_value, values[option_id])
        return values

    def _load_runtime_max_new_tokens(self, payload: Optional[Dict[str, Any]] = None) -> Optional[int]:
        payload = payload or {}
        raw_settings = payload.get("settings") if isinstance(payload, dict) else None
        if not isinstance(raw_settings, dict):
            return None
        raw_value = raw_settings.get("max_new_tokens")
        if raw_value is None:
            return None
        return self._clamp_max_new_tokens(raw_value, self.default_max_new_tokens)

    def _resolved_max_new_tokens(self, model_value: Any) -> int:
        base_value = self._clamp_max_new_tokens(model_value, self.default_max_new_tokens)
        if self.runtime_max_new_tokens is not None:
            return self._clamp_max_new_tokens(self.runtime_max_new_tokens, base_value)
        return base_value

    def _persist_engine_option_values(self):
        path = self.runtime_options_path
        if not path:
            return

        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "updated_at": time.time(),
            "options": {
                item["id"]: self._coerce_bool(
                    self.engine_option_values.get(item["id"]), item.get("default_enabled", False)
                )
                for item in self.engine_option_catalog
            },
            "settings": {
                "max_new_tokens": self.max_new_tokens,
            },
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        self.runtime_state_payload = payload

    def _engine_option_enabled(self, option_id: str) -> bool:
        normalized = self._normalize_model_id(option_id)
        item = next((row for row in self.engine_option_catalog if row["id"] == normalized), None)
        default_value = item.get("default_enabled", False) if item else False
        return self._coerce_bool(self.engine_option_values.get(normalized), default_value)

    def _apply_engine_options(self, initializing: bool = False, restart_running: bool = False):
        self.trace_enabled = self._engine_option_enabled("trace_enabled")
        self.warmup_on_model_switch = self._engine_option_enabled("warmup_on_model_switch")
        current_entry = next((item for item in self.available_models if item.get("id") == self.current_model_id), None)
        model_max_new_tokens = current_entry.get("max_new_tokens") if current_entry else None
        self.max_new_tokens = self._resolved_max_new_tokens(model_max_new_tokens)

        with self.trace_lock:
            if not self.trace_enabled:
                self.current_trace = None
                self.last_trace = {"state": "disabled", "enabled": False, "steps": []}
            elif isinstance(self.last_trace, dict) and self.last_trace.get("state") == "disabled":
                self.last_trace = None

        if initializing:
            return

        was_running = self.is_running()
        if restart_running and was_running:
            self._stop_process()

        should_restart = restart_running and (was_running or self.eager_start or self.warmup_on_model_switch)
        should_warmup = self.warmup_on_model_switch and not self.is_running() and self.active_request_id is None
        if self.is_ready() and (should_restart or should_warmup):
            self._start_engine()

    def list_engine_options(self) -> List[Dict[str, Any]]:
        items = []
        for option in self.engine_option_catalog:
            items.append(
                {
                    "id": option["id"],
                    "name": option["name"],
                    "description": option.get("description") or "",
                    "enabled": self._engine_option_enabled(option["id"]),
                    "default_enabled": self._coerce_bool(option.get("default_enabled"), False),
                    "requires_restart": self._coerce_bool(option.get("requires_restart"), False),
                    "supported": True,
                }
            )
        return items

    def engine_options_status(self) -> Dict[str, Any]:
        return {
            "current_model_id": self.current_model_id,
            "current_model_name": self.current_model_name,
            "current_model_family": self.current_model_family,
            "running": self.is_running(),
            "ready": self.is_ready(),
            "trace_enabled": self.trace_enabled,
            "warmup_on_model_switch": self.warmup_on_model_switch,
            "max_new_tokens": self.max_new_tokens,
            "default_max_new_tokens": self.default_max_new_tokens,
            "min_max_new_tokens": self.MIN_MAX_NEW_TOKENS,
            "max_max_new_tokens": self.MAX_MAX_NEW_TOKENS,
            "runtime_options_path": self.runtime_options_path,
            "options": self.list_engine_options(),
        }

    def update_engine_options(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(updates, dict) or not updates:
            return self.engine_options_status()

        normalized_updates: Dict[str, bool] = {}
        restart_required = False
        for raw_id, raw_value in updates.items():
            option_id = self._normalize_model_id(raw_id)
            option = next((row for row in self.engine_option_catalog if row["id"] == option_id), None)
            if not option:
                raise ValueError(f"未知优化项: {raw_id}")
            current_value = self._engine_option_enabled(option_id)
            next_value = self._coerce_bool(raw_value, current_value)
            normalized_updates[option_id] = next_value
            if next_value != current_value and self._coerce_bool(option.get("requires_restart"), False):
                restart_required = True

        with self.request_state_lock:
            if restart_required and self.active_request_id is not None:
                raise RuntimeError("当前有进行中的推理，请等待完成后再修改需要重启的优化项。")

        for option_id, enabled in normalized_updates.items():
            self.engine_option_values[option_id] = enabled

        self._persist_engine_option_values()
        self._apply_engine_options(restart_running=restart_required)
        return self.engine_options_status()

    def update_generation_settings(self, max_new_tokens: Optional[int] = None) -> Dict[str, Any]:
        if max_new_tokens is None:
            return self.engine_options_status()

        with self.request_state_lock:
            if self.active_request_id is not None:
                raise RuntimeError("当前有进行中的推理，请等待完成后再调整 max_token。")

        next_value = self._clamp_max_new_tokens(max_new_tokens, self.default_max_new_tokens)
        current_value = self.max_new_tokens
        self.runtime_max_new_tokens = next_value
        self.max_new_tokens = next_value
        self._persist_engine_option_values()
        self._apply_engine_options(restart_running=(next_value != current_value))
        return self.engine_options_status()

    @staticmethod
    def _strip_response_prefix(text: str) -> str:
        value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        value = value.lstrip()
        while value.startswith(":") or value.startswith("："):
            value = value[1:].lstrip()
        return value.strip()

    @classmethod
    def parse_assistant_response(cls, text: str) -> Dict[str, Any]:
        raw_content = cls._strip_response_prefix(cls._sanitize_response_text(text))
        if not raw_content:
            return {
                "raw_content": "",
                "content": "",
                "reasoning_content": None,
                "answer_content": None,
                "think_mode": False,
                "answer_complete": False,
            }

        think_start = raw_content.find(cls.THINK_OPEN_TAG)
        if think_start == -1:
            return {
                "raw_content": raw_content,
                "content": raw_content,
                "reasoning_content": None,
                "answer_content": raw_content,
                "think_mode": False,
                "answer_complete": True,
            }

        after_open = raw_content[think_start + len(cls.THINK_OPEN_TAG) :]
        think_end = after_open.find(cls.THINK_CLOSE_TAG)
        if think_end == -1:
            reasoning_content = after_open.strip() or None
            return {
                "raw_content": raw_content,
                "content": cls.THINK_NO_ANSWER_FALLBACK if reasoning_content else "",
                "reasoning_content": reasoning_content,
                "answer_content": None,
                "think_mode": True,
                "answer_complete": False,
            }

        reasoning_content = after_open[:think_end].strip() or None
        answer_content = cls._strip_response_prefix(after_open[think_end + len(cls.THINK_CLOSE_TAG) :]) or None
        display_content = answer_content or (cls.THINK_NO_ANSWER_FALLBACK if reasoning_content else "")
        return {
            "raw_content": raw_content,
            "content": display_content,
            "reasoning_content": reasoning_content,
            "answer_content": answer_content,
            "think_mode": True,
            "answer_complete": bool(answer_content),
        }

    @classmethod
    def _history_safe_content(cls, role: str, content: str) -> str:
        value = str(content or "").strip()
        if not value:
            return ""
        if role != "assistant":
            return value

        parsed = cls.parse_assistant_response(value)
        if parsed.get("answer_complete") and parsed.get("answer_content"):
            return str(parsed["answer_content"]).strip()
        if parsed.get("think_mode"):
            return ""
        normalized = cls._strip_response_prefix(value)
        if normalized == cls.THINK_NO_ANSWER_FALLBACK:
            return ""
        return normalized

    @staticmethod
    def _truncate_text(text: str, limit: int = 320) -> str:
        value = str(text or "").strip()
        if len(value) <= limit:
            return value
        if limit <= 3:
            return value[:limit]
        return value[: limit - 3] + "..."

    @staticmethod
    def _trace_step_title(step_id: str) -> str:
        mapping = {
            "tokenization": "Step1: Tokenization",
            "encoding": "Step2: Encoding",
            "transformer": "Step3: Transformer Inference",
            "sampling": "Step4: Sampling",
            "decode": "Step5: Decode",
        }
        return mapping.get(step_id, step_id)

    @staticmethod
    def _step_order(step_id: str) -> int:
        ordering = {
            "tokenization": 1,
            "encoding": 2,
            "transformer": 3,
            "sampling": 4,
            "decode": 5,
        }
        return ordering.get(step_id, 99)

    def _next_request_id(self) -> int:
        with self.counter_lock:
            self.request_counter += 1
            return self.request_counter

    def _activate_request(self, req_id: int):
        with self.request_state_lock:
            self.active_request_id = req_id
            self.cancel_requested = False
        with self.trace_lock:
            if self.current_trace:
                self.current_trace["cancel_requested"] = False
                self.last_trace = deepcopy(self.current_trace)

    def _set_cancel_requested(self, value: bool):
        with self.request_state_lock:
            if self.active_request_id is None:
                return
            self.cancel_requested = bool(value)
        with self.trace_lock:
            if self.current_trace:
                self.current_trace["cancel_requested"] = bool(value)
                self.current_trace["updated_at"] = time.time()
                self.last_trace = deepcopy(self.current_trace)

    def _is_cancel_requested(self) -> bool:
        with self.request_state_lock:
            return bool(self.active_request_id is not None and self.cancel_requested)

    def _clear_active_request(self, req_id: int):
        with self.request_state_lock:
            if self.active_request_id == req_id:
                self.active_request_id = None
                self.cancel_requested = False

    def _send_control_command(self, command: str):
        with self.stdin_lock:
            if not self.process or not self.process.stdin or self.process.stdin.closed:
                raise RuntimeError("推理进程控制通道不可用。")
            self.process.stdin.write(f"{command}\n")
            self.process.stdin.flush()

    def request_cancel(self) -> Dict[str, Any]:
        with self.request_state_lock:
            req_id = self.active_request_id
            already_requested = self.cancel_requested

        if req_id is None:
            return {
                "accepted": False,
                "request_id": None,
                "detail": "当前没有正在生成的请求。",
            }

        self._set_cancel_requested(True)
        if already_requested:
            return {
                "accepted": True,
                "request_id": req_id,
                "detail": "已请求停止当前生成。",
            }

        if not self.is_running():
            return {
                "accepted": True,
                "request_id": req_id,
                "detail": "已记录停止请求，将在当前初始化阶段结束后生效。",
            }

        try:
            self._send_control_command("[CANCEL]")
        except Exception as exc:
            self._set_cancel_requested(False)
            return {
                "accepted": False,
                "request_id": req_id,
                "detail": f"发送取消信号失败: {exc}",
            }

        return {
            "accepted": True,
            "request_id": req_id,
            "detail": "已请求停止当前生成。",
        }

    def _effective_prompt_format(self) -> str:
        if self.prompt_format in {"raw", "chatml"}:
            return self.prompt_format

        model_hint = " ".join(
            [
                self.current_model_family or "",
                self.current_model_name or "",
                os.path.basename(self.model_path or ""),
                os.path.basename(os.path.dirname(self.model_path or "")),
            ]
        ).lower()
        if any(key in model_hint for key in ("instruct", "chat", "qwen")):
            return "chatml"
        return "raw"

    def _init_trace(self, req_id: int, prompt: str, history_size: int, prompt_format: str):
        if not self.trace_enabled:
            return
        trace = {
            "request_id": req_id,
            "state": "running",
            "started_at": time.time(),
            "updated_at": time.time(),
            "cancel_requested": False,
            "history_size": int(history_size),
            "prompt_format": prompt_format,
            "prompt_preview": self._truncate_text(prompt, 280),
            "model_id": self.current_model_id,
            "model_name": self.current_model_name,
            "model_family": self.current_model_family,
            "steps": [],
        }
        with self.trace_lock:
            self.current_trace = trace
            self.last_trace = deepcopy(trace)

    def _upsert_trace_step(self, trace: Dict[str, Any], step_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        steps = trace.setdefault("steps", [])
        for step in steps:
            if step.get("id") == step_id:
                if title:
                    step["title"] = title
                return step

        step = {
            "id": step_id,
            "title": title or self._trace_step_title(step_id),
            "updated_at": time.time(),
        }
        steps.append(step)
        steps.sort(key=lambda item: self._step_order(str(item.get("id") or "")))
        return step

    def _apply_trace_event(self, event: Dict[str, Any]):
        if not self.trace_enabled:
            return
        step_id = str(event.get("step") or "").strip().lower()
        if not step_id:
            return

        with self.trace_lock:
            if not self.current_trace:
                return
            trace = self.current_trace
            trace["updated_at"] = time.time()

            if step_id == "done":
                duration = event.get("duration_seconds")
                if isinstance(duration, (int, float)):
                    trace["duration_seconds"] = float(duration)
                generated_steps = event.get("generated_steps")
                if isinstance(generated_steps, (int, float)):
                    trace["generated_steps"] = int(generated_steps)
                state = str(event.get("state") or "").strip().lower()
                if state in {"completed", "cancelled", "error"}:
                    trace["state"] = state
                self.last_trace = deepcopy(trace)
                return

            step = self._upsert_trace_step(trace, step_id, str(event.get("title") or "").strip() or None)
            step["updated_at"] = time.time()
            if isinstance(event.get("duration_ms"), (int, float)):
                step["duration_ms"] = float(event["duration_ms"])

            if step_id == "tokenization":
                if isinstance(event.get("input_text"), str):
                    step["input_text"] = self._truncate_text(event["input_text"], 320)
                if isinstance(event.get("tokens_preview"), list):
                    step["tokens_preview"] = [self._truncate_text(item, 48) for item in event["tokens_preview"][:32]]
                if isinstance(event.get("token_count"), (int, float)):
                    step["token_count"] = int(event["token_count"])
                if "truncated" in event:
                    step["truncated"] = bool(event.get("truncated"))
            elif step_id == "encoding":
                if isinstance(event.get("token_ids_preview"), list):
                    values = []
                    for item in event["token_ids_preview"][:64]:
                        try:
                            values.append(int(item))
                        except Exception:
                            continue
                    step["token_ids_preview"] = values
                if isinstance(event.get("token_count"), (int, float)):
                    step["token_count"] = int(event["token_count"])
                if "truncated" in event:
                    step["truncated"] = bool(event.get("truncated"))
            elif step_id == "transformer":
                if isinstance(event.get("operations"), list):
                    step["operations"] = [str(item) for item in event["operations"][:12]]
                if isinstance(event.get("status"), str):
                    step["status"] = event["status"]
                if isinstance(event.get("operator_count"), (int, float)):
                    step["operator_count"] = int(event["operator_count"])
                if isinstance(event.get("operator_profile"), list):
                    profile_rows = []
                    for item in event["operator_profile"][:128]:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or "").strip()
                        if not name:
                            continue
                        total_ms_raw = item.get("total_ms")
                        avg_ms_raw = item.get("avg_ms")
                        calls_raw = item.get("calls")
                        try:
                            total_ms = float(total_ms_raw) if isinstance(total_ms_raw, (int, float)) else 0.0
                        except Exception:
                            total_ms = 0.0
                        try:
                            avg_ms = float(avg_ms_raw) if isinstance(avg_ms_raw, (int, float)) else 0.0
                        except Exception:
                            avg_ms = 0.0
                        try:
                            calls = int(calls_raw) if isinstance(calls_raw, (int, float)) else 0
                        except Exception:
                            calls = 0
                        profile_rows.append(
                            {
                                "name": name,
                                "total_ms": total_ms,
                                "calls": calls,
                                "avg_ms": avg_ms,
                            }
                        )
                    profile_rows.sort(key=lambda row: row.get("total_ms", 0.0), reverse=True)
                    step["operator_profile"] = profile_rows
            elif step_id == "sampling":
                if isinstance(event.get("sampler"), str):
                    step["sampler"] = event["sampler"]
                if isinstance(event.get("generated_token_count"), (int, float)):
                    step["generated_token_count"] = int(event["generated_token_count"])
                selected_token = event.get("selected_token")
                selected_token_id = event.get("selected_token_id")
                if selected_token is not None or selected_token_id is not None:
                    selected_list = step.setdefault("selected_tokens", [])
                    selected_list.append(
                        {
                            "token": self._truncate_text(str(selected_token or ""), 64),
                            "token_id": int(selected_token_id) if isinstance(selected_token_id, (int, float)) else None,
                            "index": int(event.get("sample_index")) if isinstance(event.get("sample_index"), (int, float)) else None,
                        }
                    )
                    if len(selected_list) > 24:
                        step["selected_tokens"] = selected_list[-24:]
            elif step_id == "decode":
                if isinstance(event.get("generated_text_preview"), str):
                    step["generated_text_preview"] = self._truncate_text(event["generated_text_preview"], 380)
                if isinstance(event.get("generated_char_count"), (int, float)):
                    step["generated_char_count"] = int(event["generated_char_count"])

            self.last_trace = deepcopy(trace)

    def _consume_trace_line(self, line: str) -> bool:
        text = str(line or "").strip()
        if not text.startswith("[TRACE]"):
            return False
        if not self.trace_enabled:
            return True

        payload_text = text[len("[TRACE]") :].strip()
        if not payload_text:
            return True

        try:
            payload = json.loads(payload_text)
        except Exception:
            self._apply_trace_event(
                {
                    "step": "transformer",
                    "title": "Step3: Transformer Inference",
                    "status": "running",
                }
            )
            return True

        if isinstance(payload, dict):
            self._apply_trace_event(payload)
        return True

    def _consume_trace_block(self, stdout: str):
        if not stdout:
            return
        for raw_line in str(stdout).splitlines():
            self._consume_trace_line(raw_line)

    def _complete_trace(self, state: str, response_text: str = "", error: str = "", elapsed: Optional[float] = None):
        if not self.trace_enabled:
            return
        now = time.time()
        with self.trace_lock:
            trace = self.current_trace or self.last_trace
            if not trace:
                trace = {
                    "request_id": self.request_counter,
                    "state": state,
                    "started_at": now,
                    "updated_at": now,
                    "steps": [],
                    "model_id": self.current_model_id,
                    "model_name": self.current_model_name,
                    "model_family": self.current_model_family,
                }
            trace["state"] = state
            trace["updated_at"] = now
            trace["finished_at"] = now
            if elapsed is not None:
                trace["elapsed_seconds"] = float(elapsed)
            if response_text:
                trace["response_preview"] = self._truncate_text(response_text, 380)
            if error:
                trace["error"] = self._truncate_text(error, 380)
            self.last_trace = deepcopy(trace)
            self.current_trace = None

    def trace_status(self) -> Dict[str, Any]:
        if not self.trace_enabled:
            return {"state": "disabled", "enabled": False, "steps": []}

        with self.trace_lock:
            trace = deepcopy(self.current_trace if self.current_trace else self.last_trace)

        if not trace:
            return {"state": "idle", "steps": []}

        steps = trace.get("steps")
        if isinstance(steps, list):
            trace["steps"] = sorted(
                steps,
                key=lambda item: self._step_order(str((item or {}).get("id") or "")),
            )
        return trace

    def _tokenizer_type_from_path(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        lower_path = path.lower()
        if lower_path.endswith(".json"):
            return "bpe"
        if lower_path.endswith(".model"):
            return "spe"
        return None

    def _resolve_existing_path(self, raw_path: str, expect: str) -> Optional[str]:
        value = str(raw_path or "").strip()
        if not value:
            return None

        candidates: List[str] = []
        if os.path.isabs(value):
            candidates.append(value)
        else:
            candidates.extend(
                [
                    os.path.join(self.models_root, value),
                    os.path.join(self.engine_path, value),
                    value,
                ]
            )

        visited = set()
        for candidate in candidates:
            abs_path = os.path.abspath(candidate)
            if abs_path in visited:
                continue
            visited.add(abs_path)
            if not os.path.exists(abs_path):
                continue
            if expect == "file" and not os.path.isfile(abs_path):
                continue
            if expect == "dir" and not os.path.isdir(abs_path):
                continue
            return abs_path
        return None

    def _candidate_abs_path(self, raw_path: str) -> Optional[str]:
        value = str(raw_path or "").strip()
        if not value:
            return None
        if os.path.isabs(value):
            return os.path.abspath(value)
        for candidate in (
            os.path.join(self.models_root, value),
            os.path.join(self.engine_path, value),
            value,
        ):
            return os.path.abspath(candidate)
        return None

    def _find_model_and_tokenizer_in_dir(self, dir_path: str):
        model_file = None
        tokenizer_file = None
        tokenizer_type = None

        try:
            files = os.listdir(dir_path)
        except Exception:
            return None, None, None

        for name in files:
            full_path = os.path.join(dir_path, name)
            if not os.path.isfile(full_path):
                continue
            if name == "tokenizer.json" or (name.endswith(".json") and "tokenizer" in name.lower()):
                tokenizer_file = full_path
                tokenizer_type = "bpe"
                break

        if tokenizer_file is None:
            for name in files:
                full_path = os.path.join(dir_path, name)
                if not os.path.isfile(full_path):
                    continue
                if name.endswith(".model"):
                    tokenizer_file = full_path
                    tokenizer_type = "spe"
                    break

        for name in files:
            full_path = os.path.join(dir_path, name)
            if not os.path.isfile(full_path):
                continue
            lower_name = name.lower()
            if "tokenizer" in lower_name:
                continue
            if lower_name.endswith(".bin"):
                model_file = full_path
                break

        return model_file, tokenizer_file, tokenizer_type

    @staticmethod
    def _infer_model_family(*hints: Any) -> str:
        text = " ".join(str(item or "") for item in hints).lower()
        if "qwen3" in text:
            return "qwen3"
        if "qwen2" in text or "qwen2.5" in text:
            return "qwen2"
        if "qwen" in text:
            return "qwen2"
        return "unknown"

    def _default_executable_name(self, family: str) -> str:
        if family == "qwen3":
            return "qwen3_infer"
        return "qwen_infer"

    def _default_executable_path(self, family: str) -> str:
        return os.path.join(self.engine_path, "build", "demo", self._default_executable_name(family))

    def _resolve_model_entry(self, raw_entry: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
        model_dir_cfg = str(raw_entry.get("model_dir") or raw_entry.get("dir") or "").strip()
        model_path_cfg = str(raw_entry.get("model_path") or raw_entry.get("model") or "").strip()
        tokenizer_path_cfg = str(raw_entry.get("tokenizer_path") or raw_entry.get("tokenizer") or "").strip()
        executable_cfg = str(raw_entry.get("executable_path") or raw_entry.get("executable") or "").strip()

        resolved_dir = self._resolve_existing_path(model_dir_cfg, "dir") if model_dir_cfg else None
        resolved_model = self._resolve_existing_path(model_path_cfg, "file") if model_path_cfg else None
        resolved_tokenizer = self._resolve_existing_path(tokenizer_path_cfg, "file") if tokenizer_path_cfg else None

        tokenizer_type = self._tokenizer_type_from_path(resolved_tokenizer)

        if not resolved_model:
            infer_dir = resolved_dir or (os.path.dirname(resolved_tokenizer) if resolved_tokenizer else "")
            if infer_dir:
                resolved_model, detected_tokenizer, detected_tokenizer_type = self._find_model_and_tokenizer_in_dir(
                    infer_dir
                )
                if not resolved_tokenizer:
                    resolved_tokenizer = detected_tokenizer
                    tokenizer_type = detected_tokenizer_type
                if not resolved_dir and resolved_model:
                    resolved_dir = infer_dir

        if resolved_model and not resolved_tokenizer:
            search_dirs = []
            if resolved_dir:
                search_dirs.append(resolved_dir)
            search_dirs.append(os.path.dirname(resolved_model))
            for search_dir in search_dirs:
                _, detected_tokenizer, detected_tokenizer_type = self._find_model_and_tokenizer_in_dir(search_dir)
                if detected_tokenizer:
                    resolved_tokenizer = detected_tokenizer
                    tokenizer_type = detected_tokenizer_type
                    if not resolved_dir:
                        resolved_dir = search_dir
                    break

        model_path = resolved_model or self._candidate_abs_path(model_path_cfg)
        tokenizer_path = resolved_tokenizer or self._candidate_abs_path(tokenizer_path_cfg)
        if not model_path and resolved_dir:
            guessed_model, _, _ = self._find_model_and_tokenizer_in_dir(resolved_dir)
            model_path = guessed_model
        if not tokenizer_path and resolved_dir:
            _, guessed_tokenizer, _ = self._find_model_and_tokenizer_in_dir(resolved_dir)
            tokenizer_path = guessed_tokenizer
        if not tokenizer_type:
            tokenizer_type = self._tokenizer_type_from_path(tokenizer_path)

        family = self._infer_model_family(
            raw_entry.get("family"),
            raw_entry.get("name"),
            resolved_dir,
            model_path,
        )
        resolved_executable = (
            self._resolve_existing_path(executable_cfg, "file") if executable_cfg else self._default_executable_path(family)
        )

        name = str(raw_entry.get("name") or "").strip()
        if not name:
            name = os.path.basename(resolved_dir or os.path.dirname(model_path or "") or model_path or "default")

        model_id = str(raw_entry.get("id") or "").strip()
        if not model_id:
            model_id = self._normalize_model_id(name)

        if not model_path or not tokenizer_path:
            print(f"[Inference] 模型已配置但未就绪，缺少 model/tokenizer: {raw_entry}")
        elif not str(model_path).lower().endswith(".bin"):
            print(f"[Inference] 模型已配置但未导出 .bin: {model_path}")

        return {
            "id": model_id,
            "name": name,
            "family": family,
            "source": source,
            "dir": resolved_dir or (os.path.dirname(model_path) if model_path else None),
            "model": model_path,
            "tokenizer": tokenizer_path,
            "tokenizer_type": tokenizer_type or "unknown",
            "executable": os.path.abspath(resolved_executable) if resolved_executable else None,
            "prompt_format": str(raw_entry.get("prompt_format") or "").strip().lower() or None,
            "system_prompt": str(raw_entry.get("system_prompt") or "").strip() or None,
            "raw_with_history": raw_entry.get("raw_with_history"),
            "max_new_tokens": raw_entry.get("max_new_tokens"),
        }

    def _deduplicate_model_ids(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        used_ids: Dict[str, int] = {}
        for entry in entries:
            base_id = self._normalize_model_id(entry.get("id"))
            index = used_ids.get(base_id, 0)
            if index == 0:
                entry["id"] = base_id
            else:
                entry["id"] = f"{base_id}_{index + 1}"
            used_ids[base_id] = index + 1
        return entries

    def _parse_models_json(self) -> List[Dict[str, Any]]:
        raw = str(getattr(settings, "INFERENCE_MODELS_JSON", "") or "").strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except Exception as exc:
            print(f"[Inference] INFERENCE_MODELS_JSON 解析失败: {exc}")
            return []

        if isinstance(payload, dict):
            items = payload.get("models", [])
        elif isinstance(payload, list):
            items = payload
        else:
            print("[Inference] INFERENCE_MODELS_JSON 必须是数组或包含 models 的对象。")
            return []

        results = []
        for item in items:
            if isinstance(item, dict):
                results.append(item)
        return results

    def _legacy_model_entries(self) -> List[Dict[str, Any]]:
        configured_model_dir = str(getattr(settings, "INFERENCE_MODEL_DIR", "") or "").strip()
        configured_model_path = str(getattr(settings, "INFERENCE_MODEL_PATH", "") or "").strip()
        configured_tokenizer_path = str(getattr(settings, "INFERENCE_TOKENIZER_PATH", "") or "").strip()
        if not any([configured_model_dir, configured_model_path, configured_tokenizer_path]):
            return []

        name_hint = configured_model_dir or configured_model_path or "default"
        family = self._infer_model_family(name_hint)
        return [
            {
                "id": self._normalize_model_id(os.path.basename(name_hint)),
                "name": os.path.basename(name_hint.rstrip("/")) or "Default Model",
                "family": family,
                "model_dir": configured_model_dir,
                "model_path": configured_model_path,
                "tokenizer_path": configured_tokenizer_path,
            }
        ]

    def _auto_scan_entries(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        visited = set()

        if os.path.exists(self.models_root):
            for root, _, _ in os.walk(self.models_root):
                model_file, tokenizer_file, tokenizer_type = self._find_model_and_tokenizer_in_dir(root)
                if not model_file or not tokenizer_file:
                    continue
                model_key = os.path.abspath(model_file)
                if model_key in visited:
                    continue
                visited.add(model_key)
                name = os.path.basename(root)
                family = self._infer_model_family(name, model_file)
                entries.append(
                    {
                        "id": self._normalize_model_id(name),
                        "name": name,
                        "family": family,
                        "dir": root,
                        "model": model_file,
                        "tokenizer": tokenizer_file,
                        "tokenizer_type": tokenizer_type,
                    }
                )

        if not entries:
            model_file, tokenizer_file, tokenizer_type = self._find_model_and_tokenizer_in_dir(self.engine_path)
            if model_file and tokenizer_file:
                family = self._infer_model_family(self.engine_path, model_file)
                name = os.path.basename(self.engine_path.rstrip("/")) or "default"
                entries.append(
                    {
                        "id": self._normalize_model_id(name),
                        "name": name,
                        "family": family,
                        "dir": self.engine_path,
                        "model": model_file,
                        "tokenizer": tokenizer_file,
                        "tokenizer_type": tokenizer_type,
                    }
                )
        return entries

    def _candidate_score(self, entry: Dict[str, Any]) -> int:
        score = 0
        if entry.get("source") == "config":
            score += 10**6
        family = entry.get("family")
        if family == "qwen2":
            score += 300
        elif family == "qwen3":
            score += 260
        tokenizer_type = entry.get("tokenizer_type")
        if tokenizer_type == "bpe":
            score += 60
        name = str(entry.get("name") or "").lower()
        if "instruct" in name or "chat" in name:
            score += 20
        return score

    def _load_model_registry(self):
        print("=" * 50)
        print("扫描模型配置...")

        raw_entries = self._parse_models_json()
        source = "config"
        if not raw_entries:
            raw_entries = self._legacy_model_entries()
            source = "legacy_config"
        if not raw_entries:
            raw_entries = self._auto_scan_entries()
            source = "auto"

        resolved_entries: List[Dict[str, Any]] = []
        for raw_entry in raw_entries:
            if source == "auto":
                resolved_entry = {
                    "id": str(raw_entry.get("id") or ""),
                    "name": str(raw_entry.get("name") or ""),
                    "family": str(raw_entry.get("family") or ""),
                    "source": "auto",
                    "dir": raw_entry.get("dir"),
                    "model": raw_entry.get("model"),
                    "tokenizer": raw_entry.get("tokenizer"),
                    "tokenizer_type": raw_entry.get("tokenizer_type"),
                    "executable": self._default_executable_path(str(raw_entry.get("family") or "")),
                    "prompt_format": None,
                    "system_prompt": None,
                    "raw_with_history": None,
                    "max_new_tokens": None,
                }
            else:
                resolved_entry = self._resolve_model_entry(raw_entry, "config")
            if resolved_entry:
                resolved_entries.append(resolved_entry)

        resolved_entries = self._deduplicate_model_ids(resolved_entries)
        resolved_entries.sort(key=self._candidate_score, reverse=True)
        self.available_models = resolved_entries

        if not self.available_models:
            self._clear_selected_model()
            print("✗ 未找到可用的 .bin 模型与 tokenizer 配置")
            return

        preferred_id = self.default_model_id
        selected = None
        ready_entries = [item for item in self.available_models if self._public_model_info(item)["ready"]]
        if preferred_id:
            normalized_id = self._normalize_model_id(preferred_id)
            selected = next((item for item in ready_entries if item["id"] == normalized_id), None)
        if not selected:
            selected = ready_entries[0] if ready_entries else self.available_models[0]

        self._apply_model_entry(selected)
        print("已注册模型:")
        for item in self.available_models:
            marker = "*" if item["id"] == self.current_model_id else " "
            print(
                f"{marker} {item['id']} | {item['name']} | family={item['family']} | "
                f"model={item['model']} | exe={item.get('executable') or '(none)'}"
            )

    def _clear_selected_model(self):
        self.executable = None
        self.model_path = None
        self.tokenizer_path = None
        self.tokenizer_type = None
        self.model_selection_source = "none"
        self.current_model_id = None
        self.current_model_name = None
        self.current_model_family = None
        self.current_model_dir = None
        self.max_new_tokens = self._resolved_max_new_tokens(None)
        self.prompt_format = self.default_prompt_format
        self.raw_with_history = self.default_raw_with_history
        self.system_prompt = self.default_system_prompt

    def _apply_model_entry(self, entry: Dict[str, Any]):
        self.model_path = entry.get("model")
        self.tokenizer_path = entry.get("tokenizer")
        self.tokenizer_type = entry.get("tokenizer_type")
        self.executable = entry.get("executable")
        self.model_selection_source = entry.get("source", "auto")
        self.current_model_id = entry.get("id")
        self.current_model_name = entry.get("name")
        self.current_model_family = entry.get("family")
        self.current_model_dir = entry.get("dir")

        self.max_new_tokens = self._resolved_max_new_tokens(entry.get("max_new_tokens"))
        prompt_format = str(entry.get("prompt_format") or self.default_prompt_format).strip().lower()
        self.prompt_format = prompt_format if prompt_format in {"raw", "chatml", "auto"} else self.default_prompt_format
        self.raw_with_history = self._coerce_bool(entry.get("raw_with_history"), self.default_raw_with_history)
        self.system_prompt = str(entry.get("system_prompt") or self.default_system_prompt).strip() or self.default_system_prompt

    def _public_model_info(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        executable = entry.get("executable")
        model_path = entry.get("model")
        tokenizer_path = entry.get("tokenizer")
        executable_exists = bool(executable and os.path.exists(executable))
        ready = bool(
            executable_exists
            and model_path
            and os.path.exists(model_path)
            and tokenizer_path
            and os.path.exists(tokenizer_path)
            and entry.get("tokenizer_type") == "bpe"
            and str(model_path or "").lower().endswith(".bin")
        )
        return {
            "id": entry.get("id"),
            "name": entry.get("name"),
            "family": entry.get("family"),
            "source": entry.get("source"),
            "dir": entry.get("dir"),
            "model_path": entry.get("model"),
            "tokenizer_path": entry.get("tokenizer"),
            "tokenizer_type": entry.get("tokenizer_type"),
            "executable": executable,
            "ready": ready,
            "selected": entry.get("id") == self.current_model_id,
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [self._public_model_info(item) for item in self.available_models]

    def select_model(self, model_id: str) -> Dict[str, Any]:
        normalized_id = self._normalize_model_id(model_id)
        target = next((item for item in self.available_models if item["id"] == normalized_id), None)
        if not target:
            raise ValueError(f"模型不存在: {model_id}")

        with self.lock:
            if self.current_model_id == normalized_id:
                return self.debug_status()
            self._stop_process()
            self._apply_model_entry(target)

        if self.eager_start or self.warmup_on_model_switch:
            self._start_engine()
        return self.debug_status()

    def _process_env(self) -> Dict[str, str]:
        return {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": os.getenv("CUDA_VISIBLE_DEVICES", "0"),
            "KLLM_TRACE_ENABLED": "1" if self.trace_enabled else "0",
        }

    def _start_engine(self):
        if not self.is_ready():
            print("✗ 推理引擎配置不完整:")
            print(f"  当前模型: {self.current_model_name or '(none)'}")
            print(f"  可执行文件: {self.executable or '未找到'}")
            print(f"  模型文件: {self.model_path or '未找到'}")
            print(f"  分词器: {self.tokenizer_path or '未找到'}")
            return

        if self.is_running():
            return

        try:
            self.process = subprocess.Popen(
                [
                    self.executable,
                    "--serve",
                    self.model_path,
                    self.tokenizer_path,
                    str(self.max_new_tokens),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self.engine_path,
                env=self._process_env(),
            )
        except Exception as exc:
            print(f"✗ 推理进程启动失败: {exc}")
            self.process = None
            return

        self._start_stdout_reader()
        ready_line = self._readline_with_timeout(self.startup_timeout_seconds)
        if ready_line is None:
            if self.process and self.process.poll() is not None:
                print(f"✗ 推理进程启动失败（未收到 READY，退出码 {self.process.returncode}）")
            else:
                print(f"✗ 推理引擎启动超时（{self.startup_timeout_seconds}s，未收到 READY）")
            self._stop_process()
            return
        if ready_line.strip() != "[READY]":
            print(f"✗ 推理引擎启动异常，收到: {ready_line.strip()}")
            self._stop_process()
            return

        print("=" * 50)
        print("推理模式: 常驻进程（每条消息触发一次 generate）")
        print(f"  模型ID: {self.current_model_id}")
        print(f"  模型名称: {self.current_model_name}")
        print(f"  模型家族: {self.current_model_family}")
        print(f"  可执行文件: {self.executable}")
        print(f"  model_selection: {self.model_selection_source}")
        print(f"  模型: {os.path.basename(self.model_path)}")
        print(f"  分词器: {os.path.basename(self.tokenizer_path)}")
        print(f"  max_new_tokens: {self.max_new_tokens}")
        print(f"  prompt_format: {self.prompt_format} (effective={self._effective_prompt_format()})")
        print(f"  system_prompt: {self.system_prompt}")
        print(f"  raw_with_history: {self.raw_with_history}")
        print(f"  max_prompt_chars: {self.max_prompt_chars}")
        print(f"  timeout: {self.timeout_seconds}s")
        print(f"  trace_enabled: {self.trace_enabled}")
        print(f"  warmup_on_model_switch: {self.warmup_on_model_switch}")
        print("=" * 50)

    def _start_stdout_reader(self):
        if not self.process or not self.process.stdout:
            self.stdout_queue = None
            self.stdout_reader = None
            return

        self.stdout_queue = queue.Queue()

        def _reader(stream, line_queue: queue.Queue):
            try:
                for line in iter(stream.readline, ""):
                    line_queue.put(line)
            finally:
                line_queue.put(None)

        self.stdout_reader = threading.Thread(
            target=_reader,
            args=(self.process.stdout, self.stdout_queue),
            daemon=True,
        )
        self.stdout_reader.start()

    def _readline_with_timeout(self, timeout_seconds: float) -> Optional[str]:
        if not self.stdout_queue:
            return None
        try:
            line = self.stdout_queue.get(timeout=float(timeout_seconds))
        except queue.Empty:
            return None
        return line

    def _stop_process(self):
        if not self.process:
            return
        try:
            self._send_control_command("[EXIT]")
        except Exception:
            pass
        try:
            self.process.terminate()
            self.process.wait(timeout=3)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass
        self.process = None
        self.stdout_queue = None
        self.stdout_reader = None
        with self.request_state_lock:
            self.active_request_id = None
            self.cancel_requested = False

    def is_ready(self) -> bool:
        return all(
            [
                self.executable,
                self.model_path,
                self.tokenizer_path,
                self.tokenizer_type == "bpe",
                os.path.exists(self.executable) if self.executable else False,
                os.path.exists(self.model_path) if self.model_path else False,
                os.path.exists(self.tokenizer_path) if self.tokenizer_path else False,
            ]
        )

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def generate(self, prompt: str, history: List[Dict] = None) -> str:
        if not self.is_ready():
            return self._mock_response(prompt)

        req_id = self._next_request_id()
        start_time = time.monotonic()
        safe_history = history or []
        model_prompt = self._build_prompt(prompt, safe_history)
        effective_prompt_format = self._effective_prompt_format()
        print(
            f"[Inference][{req_id}] start: model={self.current_model_id} history={len(safe_history)} "
            f"prompt_chars={len(model_prompt)} max_new_tokens={self.max_new_tokens} "
            f"prompt_format={effective_prompt_format}"
        )
        self._init_trace(
            req_id=req_id,
            prompt=prompt,
            history_size=len(safe_history),
            prompt_format=effective_prompt_format,
        )
        self._activate_request(req_id)

        try:
            if not self.is_running():
                self._start_engine()

            if self._is_cancel_requested():
                raise InferenceCancelledError("推理已取消")

            if self.is_running():
                response = self._generate_with_process(model_prompt)
            else:
                response = self._generate_once(model_prompt)
        except InferenceCancelledError:
            elapsed = time.monotonic() - start_time
            self._complete_trace(state="cancelled", elapsed=elapsed)
            print(f"[Inference][{req_id}] cancelled: elapsed={elapsed:.2f}s")
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            error_text = f"推理异常: {exc}"
            self._complete_trace(state="error", error=error_text, elapsed=elapsed)
            print(f"[Inference][{req_id}] error: elapsed={elapsed:.2f}s detail={exc}")
            raise
        finally:
            self._clear_active_request(req_id)

        elapsed = time.monotonic() - start_time
        failed = (
            response.startswith("推理超时")
            or response.startswith("推理请求发送失败")
            or response.startswith("推理进程")
            or response.startswith("推理异常")
        )
        self._complete_trace(
            state="error" if failed else "completed",
            response_text=response,
            error=response if failed else "",
            elapsed=elapsed,
        )
        print(f"[Inference][{req_id}] done: elapsed={elapsed:.2f}s response_chars={len(response)}")
        return response

    def _build_prompt(self, prompt: str, history: List[Dict]) -> str:
        effective_prompt_format = self._effective_prompt_format()
        if effective_prompt_format == "raw":
            return self._build_raw_prompt(prompt, history)
        return self._build_chatml_prompt(prompt, history)

    def _build_raw_prompt(self, prompt: str, history: List[Dict]) -> str:
        clean_prompt = (prompt or "").strip()
        if not self.raw_with_history:
            return clean_prompt

        messages: List[Dict[str, str]] = []
        for message in history[-self.max_history_messages :]:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "")).strip().lower()
            content = message.get("content", "")
            if role not in {"user", "assistant"}:
                continue
            if not isinstance(content, str):
                content = str(content)
            content = self._history_safe_content(role, content)
            if not content:
                continue
            messages.append({"role": role, "content": content})

        if not messages or messages[-1]["role"] != "user":
            if clean_prompt:
                messages.append({"role": "user", "content": clean_prompt})

        messages = self._truncate_messages_by_chars(messages)
        parts: List[str] = []
        for message in messages:
            role_text = "用户" if message["role"] == "user" else "助手"
            parts.append(f"{role_text}: {message['content']}")
        parts.append("助手:")
        return "\n".join(parts).strip()

    def _build_chatml_prompt(self, prompt: str, history: List[Dict]) -> str:
        messages: List[Dict[str, str]] = []
        for message in history[-self.max_history_messages :]:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "")).strip().lower()
            content = message.get("content", "")
            if role not in {"system", "user", "assistant"}:
                continue
            if not isinstance(content, str):
                content = str(content)
            content = self._history_safe_content(role, content)
            if not content:
                continue
            messages.append({"role": role, "content": content})

        if not messages or messages[-1]["role"] != "user":
            clean_prompt = prompt.strip()
            if clean_prompt:
                messages.append({"role": "user", "content": clean_prompt})

        if not any(message["role"] == "system" for message in messages):
            messages.insert(0, {"role": "system", "content": self.system_prompt})

        messages = self._truncate_messages_by_chars(messages)

        parts = []
        for message in messages:
            parts.append(f"<|im_start|>{message['role']}:\n{message['content']}<|im_end|>")
        parts.append("<|im_start|>assistant:\n")
        return "\n".join(parts)

    def _truncate_messages_by_chars(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not messages or self.max_prompt_chars <= 0:
            return messages

        system_msg = None
        others = messages
        if messages[0]["role"] == "system":
            system_msg = messages[0]
            others = messages[1:]

        budget = self.max_prompt_chars
        if system_msg:
            budget -= len(system_msg["content"]) + 32
            budget = max(budget, 128)

        selected_rev: List[Dict[str, str]] = []
        used = 0
        for msg in reversed(others):
            msg_len = len(msg["content"]) + 32
            if used + msg_len <= budget:
                selected_rev.append(msg)
                used += msg_len
                continue

            if not selected_rev:
                keep = max(32, budget - 32)
                selected_rev.append({"role": msg["role"], "content": msg["content"][-keep:]})
            break

        selected = list(reversed(selected_rev))
        if system_msg:
            return [system_msg] + selected
        return selected

    def _generate_with_process(self, model_prompt: str) -> str:
        with self.lock:
            if not self.is_running() or not self.process:
                return "推理进程未运行，请稍后重试。"
            if not self.process.stdin:
                return "推理进程 stdin 不可用。"

            try:
                with self.stdin_lock:
                    self.process.stdin.write("[PROMPT_START]\n")
                    self.process.stdin.write(model_prompt)
                    if not model_prompt.endswith("\n"):
                        self.process.stdin.write("\n")
                    self.process.stdin.write("[PROMPT_END]\n")
                    self.process.stdin.flush()
            except Exception as exc:
                self._stop_process()
                return f"推理请求发送失败: {exc}"

            if self._is_cancel_requested():
                try:
                    self._send_control_command("[CANCEL]")
                except Exception as exc:
                    self._stop_process()
                    return f"推理请求发送失败: {exc}"

            response_lines: List[str] = []
            in_response = False
            cancelled = False
            deadline = time.monotonic() + float(self.timeout_seconds)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._stop_process()
                    return f"推理超时（{self.timeout_seconds}s），请减少上下文或降低生成步数。"

                line = self._readline_with_timeout(remaining)
                if line is None:
                    time.sleep(0.1)
                    if self.process.poll() is None:
                        self._stop_process()
                        return "推理进程输出中断，请检查模型输出编码或进程日志。"
                    self._stop_process()
                    return "推理进程已退出，请重试。"

                text = line.rstrip("\n")
                if self._consume_trace_line(text):
                    continue
                if text == "[CANCELLED]":
                    cancelled = True
                    continue
                if text == "[RESPONSE_START]":
                    in_response = True
                    continue
                if text == "[RESPONSE_END]":
                    break
                if in_response:
                    response_lines.append(text)

            if cancelled:
                raise InferenceCancelledError("推理已取消")
            response = self._sanitize_response_text("\n".join(response_lines).strip())
            return response if response else "（模型未生成有效回复）"

    def _generate_once(self, model_prompt: str) -> str:
        with self.lock:
            try:
                completed = subprocess.run(
                    [
                        self.executable,
                        self.model_path,
                        self.tokenizer_path,
                        model_prompt,
                        str(self.max_new_tokens),
                    ],
                    cwd=self.engine_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    env=self._process_env(),
                )
            except subprocess.TimeoutExpired:
                return f"推理超时（{self.timeout_seconds}s），请减少上下文或降低生成步数。"
            except Exception as exc:
                return f"推理进程启动失败: {exc}"

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if len(detail) > 1200:
                detail = detail[:1200] + "\n...(truncated)"
            return f"推理进程失败（退出码 {completed.returncode}）:\n{detail or '无错误输出'}"

        self._consume_trace_block(completed.stdout)
        response = self._extract_response(completed.stdout)
        response = self._sanitize_response_text(response)
        if response:
            return response
        return "（模型未生成有效回复）"

    @staticmethod
    def _extract_response(stdout: str) -> str:
        start_marker = "[RESPONSE_START]"
        end_marker = "[RESPONSE_END]"

        start_idx = stdout.find(start_marker)
        if start_idx != -1:
            start_idx += len(start_marker)
            end_idx = stdout.find(end_marker, start_idx)
            if end_idx != -1:
                return stdout[start_idx:end_idx].strip()

        lines = []
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line in {start_marker, end_marker}:
                continue
            if line.startswith("[STATS]"):
                continue
            if line.startswith("[TRACE]"):
                continue
            if line.startswith("steps:") or line.startswith("duration:") or line.startswith("steps/s:"):
                continue
            lines.append(raw_line)
        return "\n".join(lines).strip()

    @staticmethod
    def _sanitize_response_text(text: str) -> str:
        content = (text or "").strip()
        if not content:
            return ""

        lines = content.splitlines()
        if not lines:
            return content

        kept: List[str] = []
        prev_norm = ""
        same_run = 0
        for line in lines:
            norm = line.strip()
            if norm and norm == prev_norm and len(norm) <= 48:
                same_run += 1
                if same_run >= 2 and len(norm) <= 32:
                    if kept and kept[-1].strip() == norm:
                        kept.pop()
                    break
                if same_run >= 3:
                    continue
            else:
                prev_norm = norm
                same_run = 1
            kept.append(line)

        return "\n".join(kept).strip()

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
            "current_model_dir": self.current_model_dir,
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
            "engine_options": self.list_engine_options(),
            "trace_enabled": self.trace_enabled,
            "warmup_on_model_switch": self.warmup_on_model_switch,
            "max_new_tokens": self.max_new_tokens,
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

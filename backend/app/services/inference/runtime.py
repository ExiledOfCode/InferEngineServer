import json
import os
import time
from typing import Any, Dict, List, Optional

from ...config import settings


class RuntimeOptionsMixin:
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

    @classmethod
    def _read_float(cls, env_name: str, default: float) -> float:
        raw = os.getenv(env_name)
        if raw is None:
            return cls._clamp_temperature(default)
        try:
            value = float(raw)
        except ValueError:
            return cls._clamp_temperature(default)
        return cls._clamp_temperature(value)

    @staticmethod
    def _read_prompt_format(env_name: str, default: str) -> str:
        raw = str(os.getenv(env_name, default)).strip().lower()
        return raw if raw in {"raw", "chatml", "deepseek", "llama3", "tinyllama", "auto"} else default

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

    @classmethod
    def _clamp_temperature(cls, value: Any, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = default
        if parsed != parsed:
            parsed = default
        return max(cls.MIN_TEMPERATURE, min(cls.MAX_TEMPERATURE, parsed))

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
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        if configured:
            if os.path.isabs(configured):
                return os.path.abspath(configured)
            return os.path.abspath(os.path.join(backend_root, configured))
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
    def _max_new_tokens_cap_from_seq_len(cls, seq_len: Any) -> Optional[int]:
        try:
            parsed = int(seq_len)
        except Exception:
            return None
        if parsed <= 1:
            return None
        return parsed - 1

    def _current_max_new_tokens_cap(self) -> Optional[int]:
        return self._max_new_tokens_cap_from_seq_len(self.current_model_seq_len)

    @classmethod
    def _clamp_max_new_tokens(cls, value: Any, default: int, max_allowed: Optional[int] = None) -> int:
        parsed = cls._coerce_positive_int(value, default)
        parsed = max(cls.MIN_MAX_NEW_TOKENS, parsed)
        if max_allowed is not None and max_allowed > 0:
            parsed = min(parsed, max_allowed)
            parsed = max(1, parsed)
        return parsed

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

    def _load_runtime_temperature(self, payload: Optional[Dict[str, Any]] = None) -> Optional[float]:
        payload = payload or {}
        raw_settings = payload.get("settings") if isinstance(payload, dict) else None
        if not isinstance(raw_settings, dict):
            return None
        raw_value = raw_settings.get("temperature")
        if raw_value is None:
            return None
        return self._clamp_temperature(raw_value, self.default_temperature)

    def _resolved_max_new_tokens(self, model_value: Any) -> int:
        max_allowed = self._current_max_new_tokens_cap()
        base_value = self._clamp_max_new_tokens(model_value, self.default_max_new_tokens, max_allowed)
        if self.runtime_max_new_tokens is not None:
            return self._clamp_max_new_tokens(self.runtime_max_new_tokens, base_value, max_allowed)
        return base_value

    def _resolved_temperature(self, model_value: Any) -> float:
        base_value = self._clamp_temperature(model_value, self.default_temperature)
        if self.runtime_temperature is not None:
            return self._clamp_temperature(self.runtime_temperature, base_value)
        return base_value

    def _sync_runtime_max_new_tokens(self) -> bool:
        if self.runtime_max_new_tokens is None:
            return False
        normalized = self.max_new_tokens
        if self.runtime_max_new_tokens == normalized:
            return False
        self.runtime_max_new_tokens = normalized
        return True

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
                "temperature": self.temperature,
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
        self.optimized_weight_loading = self._engine_option_enabled("optimized_weight_loading")
        self.paged_kv_cache = self._engine_option_enabled("paged_kv_cache")
        self.warmup_on_model_switch = self._engine_option_enabled("warmup_on_model_switch")
        current_entry = next((item for item in self.available_models if item.get("id") == self.current_model_id), None)
        model_max_new_tokens = current_entry.get("max_new_tokens") if current_entry else None
        model_temperature = current_entry.get("temperature") if current_entry else None
        self.max_new_tokens = self._resolved_max_new_tokens(model_max_new_tokens)
        self.temperature = self._resolved_temperature(model_temperature)

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
            "current_model_supports_reasoning": self.current_model_supports_reasoning,
            "current_model_seq_len": self.current_model_seq_len,
            "running": self.is_running(),
            "ready": self.is_ready(),
            "trace_enabled": self.trace_enabled,
            "optimized_weight_loading": self.optimized_weight_loading,
            "paged_kv_cache": self.paged_kv_cache,
            "warmup_on_model_switch": self.warmup_on_model_switch,
            "max_new_tokens": self.max_new_tokens,
            "default_max_new_tokens": self.default_max_new_tokens,
            "min_max_new_tokens": self.MIN_MAX_NEW_TOKENS,
            "max_max_new_tokens": self._current_max_new_tokens_cap() or self.MAX_MAX_NEW_TOKENS,
            "temperature": self.temperature,
            "default_temperature": self.default_temperature,
            "min_temperature": self.MIN_TEMPERATURE,
            "max_temperature": self.MAX_TEMPERATURE,
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

    def update_generation_settings(
        self,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        if max_new_tokens is None and temperature is None:
            return self.engine_options_status()

        with self.request_state_lock:
            if self.active_request_id is not None:
                raise RuntimeError("当前有进行中的推理，请等待完成后再调整生成参数。")

        restart_required = False
        if max_new_tokens is not None:
            next_value = self._clamp_max_new_tokens(
                max_new_tokens, self.default_max_new_tokens, self._current_max_new_tokens_cap()
            )
            current_value = self.max_new_tokens
            self.runtime_max_new_tokens = next_value
            self.max_new_tokens = next_value
            restart_required = restart_required or next_value != current_value
        if temperature is not None:
            next_temperature = self._clamp_temperature(temperature, self.default_temperature)
            current_temperature = self.temperature
            self.runtime_temperature = next_temperature
            self.temperature = next_temperature
            restart_required = restart_required or next_temperature != current_temperature

        self._persist_engine_option_values()
        self._apply_engine_options(restart_running=restart_required)
        return self.engine_options_status()

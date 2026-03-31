import json
import os
import queue
import subprocess
import threading
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..config import settings


class InferenceService:
    """基于 KuiperLLama demo 可执行文件的推理服务。"""

    def __init__(self):
        self.engine_path = settings.INFERENCE_ENGINE_PATH
        self.executable: Optional[str] = None
        self.model_path: Optional[str] = None
        self.tokenizer_path: Optional[str] = None
        self.tokenizer_type: Optional[str] = None
        self.model_selection_source: str = "auto"
        self.current_model_id: Optional[str] = None
        self.current_model_name: Optional[str] = None
        self.current_model_family: Optional[str] = None
        self.available_models: List[Dict[str, Any]] = []
        self.last_engine_error: Optional[str] = None

        self.process: Optional[subprocess.Popen] = None
        self.stdout_queue: Optional[queue.Queue] = None
        self.stdout_reader: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        self.counter_lock = threading.Lock()
        self.trace_lock = threading.Lock()
        self.request_counter = 0
        self.current_trace: Optional[Dict[str, Any]] = None
        self.last_trace: Optional[Dict[str, Any]] = None

        legacy_max_steps = self._read_optional_positive_int("INFERENCE_MAX_STEPS")
        default_max_new_tokens = legacy_max_steps if legacy_max_steps is not None else 128
        self.max_new_tokens = self._read_positive_int("INFERENCE_MAX_NEW_TOKENS", default_max_new_tokens)
        self.timeout_seconds = self._read_positive_int("INFERENCE_TIMEOUT_SECONDS", 180)
        self.startup_timeout_seconds = self._read_positive_int("INFERENCE_STARTUP_TIMEOUT_SECONDS", 900)
        self.max_history_messages = self._read_positive_int("INFERENCE_MAX_HISTORY_MESSAGES", 8)
        self.max_prompt_chars = self._read_positive_int("INFERENCE_MAX_PROMPT_CHARS", 2400)
        self.prompt_format = self._read_prompt_format("INFERENCE_PROMPT_FORMAT", "auto")
        self.raw_with_history = self._read_bool("INFERENCE_RAW_WITH_HISTORY", False)
        self.system_prompt = (
            os.getenv("INFERENCE_SYSTEM_PROMPT", "You are a helpful assistant.").strip()
            or "You are a helpful assistant."
        )
        self.eager_start = self._read_bool("INFERENCE_EAGER_START", False)
        if self.max_new_tokens < 8:
            print(f"[WARN] INFERENCE_MAX_NEW_TOKENS={self.max_new_tokens} 偏小，可能导致回复很短。")

        self._detect_models()
        if self.eager_start and self.is_ready():
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

    def _effective_prompt_format(self) -> str:
        if self.prompt_format in {"raw", "chatml"}:
            return self.prompt_format

        model_hint = " ".join(
            [
                os.path.basename(self.model_path or ""),
                os.path.basename(os.path.dirname(self.model_path or "")),
                str(self.current_model_family or ""),
            ]
        ).lower()
        if any(key in model_hint for key in ("instruct", "chat", "qwen")):
            return "chatml"
        return "raw"

    def _next_request_id(self) -> int:
        with self.counter_lock:
            self.request_counter += 1
            return self.request_counter

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

    def _init_trace(self, req_id: int, prompt: str, history_size: int, prompt_format: str):
        trace = {
            "request_id": req_id,
            "state": "running",
            "started_at": time.time(),
            "updated_at": time.time(),
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
                self.last_trace = deepcopy(trace)
                return

            step = self._upsert_trace_step(trace, step_id, str(event.get("title") or "").strip() or None)
            step["updated_at"] = time.time()
            if isinstance(event.get("duration_ms"), (int, float)):
                step["duration_ms"] = float(event.get("duration_ms"))

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

    @staticmethod
    def _tokenizer_type_from_path(path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        lower_path = path.lower()
        if lower_path.endswith(".json"):
            return "bpe"
        if lower_path.endswith(".model"):
            return "spe"
        return None

    def _resolve_existing_path(self, raw_path: str, expect: str, models_root: str) -> Optional[str]:
        value = str(raw_path or "").strip()
        if not value:
            return None

        candidates: List[str] = []
        if os.path.isabs(value):
            candidates.append(value)
        else:
            candidates.extend(
                [
                    os.path.join(models_root, value),
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

    @staticmethod
    def _find_model_and_tokenizer_in_dir(dir_path: str):
        model_exts = (".bin", ".gguf", ".safetensors")
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

        model_candidates = []
        for name in files:
            full_path = os.path.join(dir_path, name)
            if not os.path.isfile(full_path):
                continue
            lower_name = name.lower()
            if "tokenizer" in lower_name or not lower_name.endswith(model_exts):
                continue
            if lower_name.endswith(".bin"):
                priority = 0
            elif lower_name.endswith(".gguf"):
                priority = 1
            else:
                priority = 2
            model_candidates.append((priority, full_path))

        if model_candidates:
            model_candidates.sort(key=lambda item: item[0])
            model_file = model_candidates[0][1]

        return model_file, tokenizer_file, tokenizer_type

    def _model_id_from_path(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        abs_path = os.path.abspath(path)
        try:
            rel_path = os.path.relpath(abs_path, self.engine_path)
            if not rel_path.startswith(".."):
                return rel_path.replace(os.sep, "/")
        except Exception:
            pass
        return abs_path

    @staticmethod
    def _infer_model_family(model_path: str, dir_path: str) -> str:
        hint = " ".join([os.path.basename(model_path), os.path.basename(dir_path)]).lower()
        if "qwen3" in hint:
            return "qwen3"
        if "qwen2.5" in hint or "qwen2" in hint or "qwen" in hint:
            return "qwen2"
        if "llama3" in hint:
            return "llama3"
        if "llama" in hint:
            return "llama"
        return "unknown"

    @staticmethod
    def _model_display_name(dir_path: str, model_path: str) -> str:
        dir_name = os.path.basename(dir_path.rstrip(os.sep))
        return dir_name or os.path.basename(model_path)

    def _resolve_executable_for_family(self, family: str) -> Optional[str]:
        build_demo_path = os.path.join(self.engine_path, "build", "demo")
        executable_map = {
            "qwen2": "qwen_infer",
            "qwen3": "qwen3_infer",
        }
        executable_name = executable_map.get(family)
        if not executable_name:
            return None
        executable = os.path.join(build_demo_path, executable_name)
        return executable if os.path.exists(executable) else None

    def _build_model_candidate(
        self,
        source: str,
        dir_path: str,
        model_path: str,
        tokenizer_path: str,
        tokenizer_type: Optional[str],
        configured_id: Optional[str] = None,
        configured_name: Optional[str] = None,
        configured_family: Optional[str] = None,
        configured_executable: Optional[str] = None,
    ) -> Dict[str, Any]:
        family = str(configured_family or self._infer_model_family(model_path, dir_path)).strip().lower()
        executable = configured_executable or self._resolve_executable_for_family(family)
        supported = bool(tokenizer_type == "bpe" and executable)
        unsupported_reason = None
        if tokenizer_type != "bpe":
            unsupported_reason = "当前前后端仅支持 tokenizer.json(BPE) 的服务模式"
        elif not executable:
            unsupported_reason = f"未找到 {family} 对应推理可执行文件"

        return {
            "id": str(configured_id or self._model_id_from_path(model_path)).strip(),
            "name": str(configured_name or self._model_display_name(dir_path, model_path)).strip(),
            "family": family,
            "source": source,
            "dir": dir_path,
            "model": model_path,
            "tokenizer": tokenizer_path,
            "tokenizer_type": tokenizer_type or "unknown",
            "executable": executable,
            "executable_name": os.path.basename(executable) if executable else None,
            "supported": supported,
            "unsupported_reason": unsupported_reason,
        }

    def _build_candidate_from_spec(self, spec: Dict[str, Any], models_root: str) -> Optional[Dict[str, Any]]:
        model_dir_raw = str(spec.get("dir") or spec.get("model_dir") or "").strip()
        model_path_raw = str(spec.get("model_path") or "").strip()
        tokenizer_path_raw = str(spec.get("tokenizer_path") or "").strip()
        configured_id = str(spec.get("id") or "").strip() or None
        configured_name = str(spec.get("name") or "").strip() or None
        configured_family = str(spec.get("family") or "").strip() or None
        configured_executable_raw = str(spec.get("executable_path") or spec.get("executable") or "").strip()

        resolved_dir = self._resolve_existing_path(model_dir_raw, "dir", models_root) if model_dir_raw else None
        resolved_model = self._resolve_existing_path(model_path_raw, "file", models_root) if model_path_raw else None
        resolved_tokenizer = self._resolve_existing_path(tokenizer_path_raw, "file", models_root) if tokenizer_path_raw else None
        resolved_executable = (
            self._resolve_existing_path(configured_executable_raw, "file", models_root)
            if configured_executable_raw
            else None
        )

        detected_model = None
        detected_tokenizer = None
        detected_tokenizer_type = None
        if resolved_dir:
            detected_model, detected_tokenizer, detected_tokenizer_type = self._find_model_and_tokenizer_in_dir(resolved_dir)

        model_path = resolved_model or detected_model
        tokenizer_path = resolved_tokenizer or detected_tokenizer
        tokenizer_type = self._tokenizer_type_from_path(tokenizer_path) or detected_tokenizer_type

        if not model_path or not tokenizer_path:
            print(
                f"[WARN] 跳过模型配置 {configured_name or configured_id or model_dir_raw or model_path_raw}: "
                "模型文件或 tokenizer 缺失"
            )
            return None

        if not resolved_dir:
            resolved_dir = os.path.dirname(model_path)

        return self._build_model_candidate(
            source="catalog",
            dir_path=resolved_dir,
            model_path=model_path,
            tokenizer_path=tokenizer_path,
            tokenizer_type=tokenizer_type,
            configured_id=configured_id,
            configured_name=configured_name,
            configured_family=configured_family,
            configured_executable=resolved_executable,
        )

    @staticmethod
    def _candidate_priority(candidate: Dict[str, Any]) -> int:
        score = 0
        if candidate.get("source") in {"config", "catalog"}:
            score += 1000
        if candidate.get("supported"):
            score += 200
        family = candidate.get("family")
        if family == "qwen3":
            score += 60
        elif family == "qwen2":
            score += 50
        elif family == "llama3":
            score += 20
        if candidate.get("tokenizer_type") == "bpe":
            score += 30
        model_name = os.path.basename(str(candidate.get("model") or "")).lower()
        if model_name.endswith(".bin"):
            score += 20
        elif model_name.endswith(".safetensors"):
            score -= 10
        return score

    def _serialize_model(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        current = candidate.get("id") == self.current_model_id
        return {
            "id": candidate.get("id"),
            "name": candidate.get("name"),
            "family": candidate.get("family"),
            "source": candidate.get("source"),
            "supported": bool(candidate.get("supported")),
            "unsupported_reason": candidate.get("unsupported_reason"),
            "tokenizer_type": candidate.get("tokenizer_type"),
            "executable_name": candidate.get("executable_name"),
            "model_path": candidate.get("model"),
            "tokenizer_path": candidate.get("tokenizer"),
            "current": current,
            "running": current and self.is_running(),
        }

    def _clear_selected_model(self):
        self.executable = None
        self.model_path = None
        self.tokenizer_path = None
        self.tokenizer_type = None
        self.model_selection_source = "none"
        self.current_model_id = None
        self.current_model_name = None
        self.current_model_family = None

    def _apply_selected_candidate(self, candidate: Dict[str, Any]):
        self.current_model_id = candidate.get("id")
        self.current_model_name = candidate.get("name")
        self.current_model_family = candidate.get("family")
        self.model_selection_source = candidate.get("source", "auto")
        self.model_path = candidate.get("model")
        self.tokenizer_path = candidate.get("tokenizer")
        self.tokenizer_type = candidate.get("tokenizer_type")
        self.executable = candidate.get("executable")
        self.last_engine_error = candidate.get("unsupported_reason")

    def _detect_models(self):
        build_demo_path = os.path.join(self.engine_path, "build", "demo")
        models_root = os.path.join(self.engine_path, "models")

        print("=" * 50)
        print("扫描模型文件...")
        print(f"  engine_path: {self.engine_path}")
        print(f"  demo_path: {build_demo_path}")

        candidates: List[Dict[str, Any]] = []
        configured_candidate_id: Optional[str] = None
        configured_catalog = list(getattr(settings, "INFERENCE_MODEL_SPECS", []) or [])

        if configured_catalog:
            print(f"  检测到模型目录配置，共 {len(configured_catalog)} 项。")
            for spec in configured_catalog:
                candidate = self._build_candidate_from_spec(spec, models_root)
                if not candidate:
                    continue
                candidates.append(candidate)
                if configured_candidate_id is None:
                    configured_candidate_id = candidate.get("id")
                print(
                    f"    catalog: {candidate.get('name')} [{candidate.get('family')}] "
                    f"model={candidate.get('model')}"
                )

        configured_model_dir = str(getattr(settings, "INFERENCE_MODEL_DIR", "") or "").strip()
        configured_model_path = str(getattr(settings, "INFERENCE_MODEL_PATH", "") or "").strip()
        configured_tokenizer_path = str(getattr(settings, "INFERENCE_TOKENIZER_PATH", "") or "").strip()
        has_explicit_config = any([configured_model_dir, configured_model_path, configured_tokenizer_path]) and not configured_catalog

        if has_explicit_config:
            print("  检测到显式模型配置，优先将其作为默认模型。")
            print(f"    INFERENCE_MODEL_DIR: {configured_model_dir or '(empty)'}")
            print(f"    INFERENCE_MODEL_PATH: {configured_model_path or '(empty)'}")
            print(f"    INFERENCE_TOKENIZER_PATH: {configured_tokenizer_path or '(empty)'}")

            explicit_dir = None
            explicit_model = None
            explicit_tokenizer = None
            explicit_tokenizer_type = None
            config_valid = True

            if configured_model_dir:
                explicit_dir = self._resolve_existing_path(configured_model_dir, "dir", models_root)
                if not explicit_dir:
                    config_valid = False
                    print(f"[WARN] INFERENCE_MODEL_DIR 无效，已回退为自动扫描: {configured_model_dir}")

            if config_valid and configured_model_path:
                explicit_model = self._resolve_existing_path(configured_model_path, "file", models_root)
                if not explicit_model:
                    config_valid = False
                    print(f"[WARN] INFERENCE_MODEL_PATH 无效，已回退为自动扫描: {configured_model_path}")

            if config_valid and configured_tokenizer_path:
                explicit_tokenizer = self._resolve_existing_path(configured_tokenizer_path, "file", models_root)
                if not explicit_tokenizer:
                    config_valid = False
                    print(f"[WARN] INFERENCE_TOKENIZER_PATH 无效，已回退为自动扫描: {configured_tokenizer_path}")

            if config_valid:
                selected_dir = explicit_dir

                if not explicit_model:
                    infer_dir = explicit_dir
                    if not infer_dir and explicit_tokenizer:
                        infer_dir = os.path.dirname(explicit_tokenizer)
                    if infer_dir:
                        explicit_model, detected_tokenizer, detected_tokenizer_type = self._find_model_and_tokenizer_in_dir(
                            infer_dir
                        )
                        if explicit_model:
                            selected_dir = infer_dir
                            if not explicit_tokenizer:
                                explicit_tokenizer = detected_tokenizer
                                explicit_tokenizer_type = detected_tokenizer_type
                    if not explicit_model:
                        config_valid = False
                        print("[WARN] 显式配置未能定位到完整模型，将继续自动扫描。")

                if config_valid and not explicit_tokenizer and explicit_model:
                    tokenizer_search_dirs = []
                    if explicit_dir:
                        tokenizer_search_dirs.append(explicit_dir)
                    tokenizer_search_dirs.append(os.path.dirname(explicit_model))

                    for search_dir in tokenizer_search_dirs:
                        _, detected_tokenizer, detected_tokenizer_type = self._find_model_and_tokenizer_in_dir(search_dir)
                        if detected_tokenizer:
                            explicit_tokenizer = detected_tokenizer
                            explicit_tokenizer_type = detected_tokenizer_type
                            if not selected_dir:
                                selected_dir = search_dir
                            break

                if config_valid and explicit_tokenizer and not explicit_tokenizer_type:
                    explicit_tokenizer_type = self._tokenizer_type_from_path(explicit_tokenizer)

                if config_valid and explicit_model and explicit_tokenizer:
                    if not selected_dir:
                        selected_dir = os.path.dirname(explicit_model)
                    candidate = self._build_model_candidate(
                        source="config",
                        dir_path=selected_dir,
                        model_path=explicit_model,
                        tokenizer_path=explicit_tokenizer,
                        tokenizer_type=explicit_tokenizer_type,
                    )
                    configured_candidate_id = candidate.get("id")
                    candidates.append(candidate)
                    print("  已根据显式配置定位模型:")
                    print(f"    目录: {selected_dir}")
                    print(f"    模型: {explicit_model}")
                    print(f"    分词器: {explicit_tokenizer} ({explicit_tokenizer_type or 'unknown'})")

        visited_dirs = set()
        if not configured_catalog:
            if os.path.exists(models_root):
                for root, _, _ in os.walk(models_root):
                    abs_root = os.path.abspath(root)
                    if abs_root in visited_dirs:
                        continue
                    visited_dirs.add(abs_root)
                    model_file, tokenizer_file, tokenizer_type = self._find_model_and_tokenizer_in_dir(abs_root)
                    if model_file and tokenizer_file:
                        candidates.append(
                            self._build_model_candidate(
                                source="auto",
                                dir_path=abs_root,
                                model_path=model_file,
                                tokenizer_path=tokenizer_file,
                                tokenizer_type=tokenizer_type,
                            )
                        )

            engine_root = os.path.abspath(self.engine_path)
            if engine_root not in visited_dirs:
                model_file, tokenizer_file, tokenizer_type = self._find_model_and_tokenizer_in_dir(engine_root)
                if model_file and tokenizer_file:
                    candidates.append(
                        self._build_model_candidate(
                            source="auto",
                            dir_path=engine_root,
                            model_path=model_file,
                            tokenizer_path=tokenizer_file,
                            tokenizer_type=tokenizer_type,
                        )
                    )

        if not candidates:
            print("✗ 未找到可用模型目录")
            self.available_models = []
            self._clear_selected_model()
            self.last_engine_error = "未找到可用的模型和分词器"
            return

        deduped: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            candidate_id = str(candidate.get("id") or "")
            if not candidate_id:
                continue
            current = deduped.get(candidate_id)
            if current is None or self._candidate_priority(candidate) > self._candidate_priority(current):
                deduped[candidate_id] = candidate

        ordered_candidates = sorted(deduped.values(), key=self._candidate_priority, reverse=True)
        self.available_models = ordered_candidates

        print(f"  共发现 {len(ordered_candidates)} 个模型候选:")
        for item in ordered_candidates:
            support_text = "supported" if item.get("supported") else f"unsupported: {item.get('unsupported_reason')}"
            print(
                f"    - {item.get('name')} [{item.get('family')}] "
                f"{os.path.basename(str(item.get('model') or ''))} ({support_text})"
            )

        selected = None
        if self.current_model_id:
            selected = next((item for item in ordered_candidates if item.get("id") == self.current_model_id), None)
        if not selected and configured_candidate_id:
            selected = next((item for item in ordered_candidates if item.get("id") == configured_candidate_id), None)
        if not selected:
            selected = next((item for item in ordered_candidates if item.get("supported")), None)
        if not selected:
            selected = ordered_candidates[0]

        self._apply_selected_candidate(selected)
        print("=" * 50)
        print("已选择当前模型:")
        source_label = {
            "catalog": "模型目录配置",
            "config": "显式配置",
            "auto": "自动扫描",
        }.get(self.model_selection_source, self.model_selection_source)
        print(f"  来源: {source_label}")
        print(f"  名称: {self.current_model_name}")
        print(f"  家族: {self.current_model_family}")
        print(f"  模型: {self.model_path}")
        print(f"  分词器: {self.tokenizer_path}")
        print(f"  可执行文件: {self.executable or '未找到'}")
        if self.last_engine_error:
            print(f"  限制: {self.last_engine_error}")

    def _find_candidate_by_id(self, model_id: Optional[str]) -> Optional[Dict[str, Any]]:
        target = str(model_id or "").strip()
        if not target:
            return None
        for candidate in self.available_models:
            if candidate.get("id") == target:
                return candidate
        return None

    def refresh_models(self):
        with self.lock:
            self._detect_models()

    def list_models(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [self._serialize_model(candidate) for candidate in self.available_models]

    def switch_model(self, model_id: str, start: bool = True) -> Dict[str, object]:
        with self.lock:
            candidate = self._find_candidate_by_id(model_id)
            if not candidate:
                raise ValueError(f"未找到模型: {model_id}")
            if not candidate.get("supported"):
                raise ValueError(candidate.get("unsupported_reason") or "该模型当前无法用于服务模式")

            same_model = candidate.get("id") == self.current_model_id
            if same_model and self.is_running():
                return self.debug_status()

            if self.is_running():
                print(f"[Inference] 切换模型前先停止当前进程: {self.current_model_name}")
                self._stop_process()

            self._apply_selected_candidate(candidate)
            print(f"[Inference] 已切换当前模型 -> {self.current_model_name} ({self.current_model_family})")

            if start:
                self._start_engine()

            return self.debug_status()

    def _start_engine(self):
        self.last_engine_error = None
        if not self.is_ready():
            self.last_engine_error = "推理引擎配置不完整"
            print("✗ 推理引擎配置不完整:")
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
                bufsize=1,
                cwd=self.engine_path,
                env={
                    **os.environ,
                    "CUDA_VISIBLE_DEVICES": os.getenv("CUDA_VISIBLE_DEVICES", "0"),
                },
            )
        except Exception as exc:
            self.last_engine_error = f"推理进程启动失败: {exc}"
            print(f"✗ {self.last_engine_error}")
            self.process = None
            return

        self._start_stdout_reader()
        ready_line = self._readline_with_timeout(self.startup_timeout_seconds)
        if ready_line is None:
            if self.process and self.process.poll() is not None:
                self.last_engine_error = f"推理进程启动失败（未收到 READY，退出码 {self.process.returncode}）"
            else:
                self.last_engine_error = f"推理引擎启动超时（{self.startup_timeout_seconds}s，未收到 READY）"
            print(f"✗ {self.last_engine_error}")
            self._stop_process()
            return
        if ready_line.strip() != "[READY]":
            self.last_engine_error = f"推理引擎启动异常，收到: {ready_line.strip()}"
            print(f"✗ {self.last_engine_error}")
            self._stop_process()
            return

        print("=" * 50)
        print("推理模式: 常驻进程（每条消息触发一次 generate）")
        print(f"  当前模型: {self.current_model_name} ({self.current_model_family})")
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
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.write("[EXIT]\n")
                self.process.stdin.flush()
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

    def is_ready(self) -> bool:
        return all([self.executable, self.model_path, self.tokenizer_path])

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def generate(self, prompt: str, history: List[Dict] = None, model_id: Optional[str] = None) -> str:
        with self.lock:
            if model_id:
                self.switch_model(model_id, start=False)

            if not self.is_ready():
                return self._mock_response(prompt)

            req_id = self._next_request_id()
            start_time = time.monotonic()
            safe_history = history or []
            model_prompt = self._build_prompt(prompt, safe_history)
            effective_prompt_format = self._effective_prompt_format()
            print(
                f"[Inference][{req_id}] start: model={self.current_model_name} family={self.current_model_family} "
                f"history={len(safe_history)} prompt_chars={len(model_prompt)} "
                f"max_new_tokens={self.max_new_tokens} prompt_format={effective_prompt_format}"
            )
            self._init_trace(
                req_id=req_id,
                prompt=prompt,
                history_size=len(safe_history),
                prompt_format=effective_prompt_format,
            )

            if not self.is_running():
                self._start_engine()

            if self.is_running():
                response = self._generate_with_process(model_prompt)
            else:
                response = self._generate_once(model_prompt)

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
            content = content.strip()
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
            content = content.strip()
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
            parts.append(f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
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
        if not self.is_running() or not self.process:
            return "推理进程未运行，请稍后重试。"
        if not self.process.stdin:
            return "推理进程 stdin 不可用。"

        try:
            self.process.stdin.write("[PROMPT_START]\n")
            self.process.stdin.write(model_prompt)
            if not model_prompt.endswith("\n"):
                self.process.stdin.write("\n")
            self.process.stdin.write("[PROMPT_END]\n")
            self.process.stdin.flush()
        except Exception as exc:
            self._stop_process()
            return f"推理请求发送失败: {exc}"

        response_lines: List[str] = []
        in_response = False
        deadline = time.monotonic() + float(self.timeout_seconds)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._stop_process()
                return f"推理超时（{self.timeout_seconds}s），请减少上下文或降低生成步数。"

            line = self._readline_with_timeout(remaining)
            if line is None:
                if self.process.poll() is None:
                    self._stop_process()
                    return f"推理超时（{self.timeout_seconds}s），请减少上下文或降低生成步数。"
                self._stop_process()
                return "推理进程已退出，请重试。"

            text = line.rstrip("\n")
            if self._consume_trace_line(text):
                continue
            if text == "[RESPONSE_START]":
                in_response = True
                continue
            if text == "[RESPONSE_END]":
                break
            if in_response:
                response_lines.append(text)

        response = self._sanitize_response_text("\n".join(response_lines).strip())
        return response if response else "（模型未生成有效回复）"

    def _generate_once(self, model_prompt: str) -> str:
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
                timeout=self.timeout_seconds,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": os.getenv("CUDA_VISIBLE_DEVICES", "0")},
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
        current_candidate = self._find_candidate_by_id(self.current_model_id)
        current_model = self._serialize_model(current_candidate) if current_candidate else None
        return {
            "ready": self.is_ready(),
            "running": self.is_running(),
            "engine_path": self.engine_path,
            "executable": self.executable,
            "model_selection_source": self.model_selection_source,
            "model_path": self.model_path,
            "tokenizer_path": self.tokenizer_path,
            "tokenizer_type": self.tokenizer_type,
            "configured_model_dir": settings.INFERENCE_MODEL_DIR,
            "configured_model_path": settings.INFERENCE_MODEL_PATH,
            "configured_tokenizer_path": settings.INFERENCE_TOKENIZER_PATH,
            "current_model_id": self.current_model_id,
            "current_model_name": self.current_model_name,
            "current_model_family": self.current_model_family,
            "current_model": current_model,
            "available_models_count": len(self.available_models),
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
            "last_engine_error": self.last_engine_error,
        }

    def _mock_response(self, prompt: str) -> str:
        return f"""推理引擎未就绪。

你的问题是: {prompt}

请检查:
- 当前模型: {self.current_model_name or '未选择'}
- 可执行文件: {'✓' if self.executable else '❌ 未找到'}
- 模型文件: {'✓' if self.model_path else '❌ 未找到'}
- 分词器(tokenizer.json): {'✓' if self.tokenizer_path else '❌ 未找到'}
- 额外信息: {self.last_engine_error or '无'}
"""

    def clear_history(self):
        return None

    def shutdown(self):
        with self.lock:
            self._stop_process()


inference_service = InferenceService()

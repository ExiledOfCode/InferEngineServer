import json
import os
import struct
from typing import Any, Dict, List, Optional

from ...config import settings


class ModelRegistryMixin:
    def _tokenizer_type_from_path(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        lower_path = path.lower()
        if lower_path.endswith(".json"):
            return "bpe"
        if lower_path.endswith(".model"):
            return "spe"
        return None

    def _supports_paged_kv_cache(self) -> bool:
        return self.current_model_family in {"qwen2", "qwen3", "deepseek_qwen"}

    def _supports_optimized_weight_loading(self) -> bool:
        return self.current_model_family in {"qwen2", "qwen3"}

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
            if name.endswith(".model"):
                tokenizer_file = full_path
                tokenizer_type = "spe"
                break

        if tokenizer_file is None:
            for name in files:
                full_path = os.path.join(dir_path, name)
                if not os.path.isfile(full_path):
                    continue
                if name == "tokenizer.json" or (name.endswith(".json") and "tokenizer" in name.lower()):
                    tokenizer_file = full_path
                    tokenizer_type = "bpe"
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

    @classmethod
    def _read_model_seq_len(cls, model_path: Optional[str]) -> Optional[int]:
        if not model_path or not str(model_path).lower().endswith(".bin"):
            return None
        try:
            with open(model_path, "rb") as fh:
                header = fh.read(64)
        except Exception as exc:
            print(f"[Inference] 读取模型 seq_len 失败: {model_path}: {exc}")
            return None

        if len(header) < 28:
            return None

        try:
            magic = struct.unpack_from("<I", header, 0)[0]
            config_offset = 16 if magic == cls.MODEL_FILE_MAGIC else 0
            if len(header) < config_offset + 28:
                return None
            seq_len = struct.unpack_from("<iiiiiii", header, config_offset)[6]
        except Exception as exc:
            print(f"[Inference] 解析模型 seq_len 失败: {model_path}: {exc}")
            return None

        if seq_len <= 0 or seq_len > 1_000_000:
            print(f"[Inference] 模型 seq_len 异常: {model_path}: {seq_len}")
            return None
        return seq_len

    @staticmethod
    def _infer_model_family(*hints: Any) -> str:
        text = " ".join(str(item or "") for item in hints).lower()
        if "deepseek" in text and "qwen" in text:
            return "deepseek_qwen"
        if "deepseek" in text and "llama" in text:
            return "deepseek_llama"
        if "llama-3" in text or "llama 3" in text or "llama3" in text:
            return "llama3"
        if "qwen3" in text:
            return "qwen3"
        if "qwen2" in text or "qwen2.5" in text:
            return "qwen2"
        if "qwen" in text:
            return "qwen2"
        if "tinyllama" in text:
            return "tinyllama"
        if "smollm" in text:
            return "smollm"
        if "llama" in text:
            return "llama"
        return "unknown"

    def _default_executable_name(self, family: str) -> str:
        if family == "qwen3":
            return "qwen3_infer"
        if family == "llama3":
            return "llama3_infer"
        if family == "tinyllama":
            return "tinyllama_infer"
        if family == "smollm":
            return "smollm_infer"
        if family == "deepseek_qwen":
            return "deepseek_qwen_infer"
        if family == "deepseek_llama":
            return "deepseek_llama_infer"
        if family == "llama":
            return "llama_infer"
        return "qwen_infer"

    def _default_executable_path(self, family: str) -> str:
        if family == "deepseek_qwen":
            return os.path.join(self.engine_path, "demo", "deepseek_qwen_infer.py")
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
            "temperature": raw_entry.get("temperature"),
            "seq_len": self._read_model_seq_len(model_path),
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
        elif family in {"deepseek_qwen", "llama", "llama3", "tinyllama", "smollm", "deepseek_llama"}:
            score += 220
        tokenizer_type = entry.get("tokenizer_type")
        if tokenizer_type == "bpe":
            score += 60
        elif tokenizer_type == "spe":
            score += 40
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
                    "temperature": None,
                    "seq_len": self._read_model_seq_len(raw_entry.get("model")),
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
                f"seq_len={item.get('seq_len') or '-'} | model={item['model']} | "
                f"exe={item.get('executable') or '(none)'}"
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
        self.current_model_seq_len = None
        self.max_new_tokens = self._resolved_max_new_tokens(None)
        self.temperature = self._resolved_temperature(None)
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
        self.current_model_seq_len = entry.get("seq_len")

        self.max_new_tokens = self._resolved_max_new_tokens(entry.get("max_new_tokens"))
        self.temperature = self._resolved_temperature(entry.get("temperature"))
        runtime_settings_changed = self._sync_runtime_max_new_tokens()
        prompt_format = str(entry.get("prompt_format") or self.default_prompt_format).strip().lower()
        self.prompt_format = (
            prompt_format
            if prompt_format in {"raw", "chatml", "deepseek", "llama3", "tinyllama", "auto"}
            else self.default_prompt_format
        )
        self.raw_with_history = self._coerce_bool(entry.get("raw_with_history"), self.default_raw_with_history)
        self.system_prompt = str(entry.get("system_prompt") or self.default_system_prompt).strip() or self.default_system_prompt
        if runtime_settings_changed:
            self._persist_engine_option_values()

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
            "seq_len": entry.get("seq_len"),
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

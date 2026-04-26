import json
import os
import time
from typing import Any, Dict, List, Optional

from ...config import settings


class OperatorOptionsMixin:
    def _resolve_operator_options_path(self) -> str:
        configured = str(getattr(settings, "INFERENCE_OPERATOR_OPTIONS_PATH", "") or "").strip()
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        if configured:
            if os.path.isabs(configured):
                return os.path.abspath(configured)
            return os.path.abspath(os.path.join(backend_root, configured))
        return os.path.join(backend_root, "runtime", "operator_options.json")

    def _load_operator_payload(self) -> Dict[str, Any]:
        path = self.operator_options_path
        if not path or not os.path.exists(path):
            return {}

        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            print(f"[Inference] 算子配置读取失败: {exc}")
            return {}

        return payload if isinstance(payload, dict) else {}

    def _parse_operator_options_config(self) -> List[Dict[str, Any]]:
        raw = str(getattr(settings, "INFERENCE_OPERATOR_OPTIONS_JSON", "") or "").strip()
        if not raw:
            return []

        try:
            payload = json.loads(raw)
        except Exception as exc:
            print(f"[Inference] INFERENCE_OPERATOR_OPTIONS_JSON 解析失败: {exc}")
            return []

        if isinstance(payload, dict):
            items = payload.get("groups", [])
        elif isinstance(payload, list):
            items = payload
        else:
            return []

        results = []
        for item in items:
            if isinstance(item, dict):
                results.append(item)
        return results

    def _merge_operator_choices(
        self,
        existing_choices: Optional[List[Dict[str, Any]]],
        raw_choices: Any,
    ) -> List[Dict[str, Any]]:
        order: List[str] = []
        catalog: Dict[str, Dict[str, Any]] = {}

        for item in existing_choices or []:
            choice_id = self._normalize_model_id(item.get("id"))
            if not choice_id:
                continue
            order.append(choice_id)
            catalog[choice_id] = {
                "id": choice_id,
                "name": str(item.get("name") or choice_id).strip() or choice_id,
                "description": str(item.get("description") or "").strip(),
                "supported": self._coerce_bool(item.get("supported"), True),
            }

        if not isinstance(raw_choices, list):
            return [catalog[choice_id] for choice_id in order]

        for item in raw_choices:
            if not isinstance(item, dict):
                continue
            choice_id = self._normalize_model_id(item.get("id"))
            if not choice_id:
                continue
            if choice_id not in catalog:
                order.append(choice_id)
                catalog[choice_id] = {
                    "id": choice_id,
                    "name": choice_id,
                    "description": "",
                    "supported": True,
                }

            catalog[choice_id]["name"] = str(item.get("name") or catalog[choice_id]["name"]).strip() or choice_id
            catalog[choice_id]["description"] = str(
                item.get("description") or catalog[choice_id]["description"]
            ).strip()
            if "supported" in item:
                catalog[choice_id]["supported"] = self._coerce_bool(
                    item.get("supported"), catalog[choice_id]["supported"]
                )

        return [catalog[choice_id] for choice_id in order]

    def _normalize_operator_default(self, group: Dict[str, Any]) -> str:
        default_selected = self._normalize_model_id(group.get("default_selected"))
        choices = [item for item in group.get("choices", []) if self._coerce_bool(item.get("supported"), True)]
        choice_ids = {item["id"] for item in choices}
        if default_selected in choice_ids:
            return default_selected
        if choices:
            return choices[0]["id"]
        return ""

    def _load_operator_group_catalog(self) -> List[Dict[str, Any]]:
        order: List[str] = []
        catalog: Dict[str, Dict[str, Any]] = {}

        for item in self.DEFAULT_OPERATOR_OPTIONS:
            group_id = self._normalize_model_id(item.get("id"))
            if not group_id:
                continue
            order.append(group_id)
            catalog[group_id] = {
                "id": group_id,
                "name": str(item.get("name") or group_id).strip() or group_id,
                "description": str(item.get("description") or "").strip(),
                "env_var": str(item.get("env_var") or "").strip(),
                "requires_restart": self._coerce_bool(item.get("requires_restart"), True),
                "default_selected": self._normalize_model_id(item.get("default_selected")),
                "choices": self._merge_operator_choices([], item.get("choices")),
            }
            catalog[group_id]["default_selected"] = self._normalize_operator_default(catalog[group_id])

        for raw_item in self._parse_operator_options_config():
            group_id = self._normalize_model_id(raw_item.get("id"))
            if not group_id:
                continue
            if group_id not in catalog:
                order.append(group_id)
                catalog[group_id] = {
                    "id": group_id,
                    "name": group_id,
                    "description": "",
                    "env_var": "",
                    "requires_restart": True,
                    "default_selected": "",
                    "choices": [],
                }

            catalog[group_id]["name"] = str(raw_item.get("name") or catalog[group_id]["name"]).strip() or group_id
            catalog[group_id]["description"] = str(
                raw_item.get("description") or catalog[group_id]["description"]
            ).strip()
            if "env_var" in raw_item:
                catalog[group_id]["env_var"] = str(raw_item.get("env_var") or catalog[group_id]["env_var"]).strip()
            if "requires_restart" in raw_item:
                catalog[group_id]["requires_restart"] = self._coerce_bool(
                    raw_item.get("requires_restart"), catalog[group_id]["requires_restart"]
                )
            if "default_selected" in raw_item:
                catalog[group_id]["default_selected"] = self._normalize_model_id(raw_item.get("default_selected"))
            if "choices" in raw_item:
                catalog[group_id]["choices"] = self._merge_operator_choices(
                    catalog[group_id]["choices"], raw_item.get("choices")
                )
            catalog[group_id]["default_selected"] = self._normalize_operator_default(catalog[group_id])

        return [catalog[group_id] for group_id in order]

    def _is_valid_operator_choice(self, group: Dict[str, Any], choice_id: str) -> bool:
        for item in group.get("choices", []):
            if item["id"] == choice_id and self._coerce_bool(item.get("supported"), True):
                return True
        return False

    def _load_operator_option_values(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        values = {
            group["id"]: self._normalize_operator_default(group)
            for group in self.operator_group_catalog
        }

        payload = payload or {}
        raw_options = payload.get("operators") if isinstance(payload, dict) else None
        if not isinstance(raw_options, dict):
            return values

        for raw_id, raw_value in raw_options.items():
            group_id = self._normalize_model_id(raw_id)
            choice_id = self._normalize_model_id(raw_value)
            group = next((item for item in self.operator_group_catalog if item["id"] == group_id), None)
            if group and self._is_valid_operator_choice(group, choice_id):
                values[group_id] = choice_id
        return values

    def _operator_choice(self, group_id: str) -> str:
        normalized = self._normalize_model_id(group_id)
        group = next((item for item in self.operator_group_catalog if item["id"] == normalized), None)
        if not group:
            return ""

        selected = self._normalize_model_id(self.operator_option_values.get(normalized))
        if self._is_valid_operator_choice(group, selected):
            return selected
        fallback = self._normalize_operator_default(group)
        self.operator_option_values[normalized] = fallback
        return fallback

    def list_operator_groups(self) -> List[Dict[str, Any]]:
        groups = []
        for group in self.operator_group_catalog:
            groups.append(
                {
                    "id": group["id"],
                    "name": group["name"],
                    "description": group.get("description") or "",
                    "selected": self._operator_choice(group["id"]),
                    "default_selected": self._normalize_operator_default(group),
                    "requires_restart": self._coerce_bool(group.get("requires_restart"), True),
                    "choices": [
                        {
                            "id": choice["id"],
                            "name": choice["name"],
                            "description": choice.get("description") or "",
                            "supported": self._coerce_bool(choice.get("supported"), True),
                            "default_selected": choice["id"] == self._normalize_operator_default(group),
                        }
                        for choice in group.get("choices", [])
                    ],
                }
            )
        return groups

    def operator_options_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running(),
            "ready": self.is_ready(),
            "runtime_options_path": self.operator_options_path,
            "groups": self.list_operator_groups(),
        }

    def _persist_operator_option_values(self):
        path = self.operator_options_path
        if not path:
            return

        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "updated_at": time.time(),
            "operators": {
                group["id"]: self._operator_choice(group["id"])
                for group in self.operator_group_catalog
            },
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        self.operator_state_payload = payload

    def operator_process_env(self) -> Dict[str, str]:
        env_map: Dict[str, str] = {}
        for group in self.operator_group_catalog:
            env_var = str(group.get("env_var") or "").strip()
            selected = self._operator_choice(group["id"])
            if env_var and selected:
                env_map[env_var] = selected
        return env_map

    def update_operator_options(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(updates, dict) or not updates:
            return self.operator_options_status()

        normalized_updates: Dict[str, str] = {}
        restart_required = False
        for raw_group_id, raw_choice_id in updates.items():
            group_id = self._normalize_model_id(raw_group_id)
            choice_id = self._normalize_model_id(raw_choice_id)
            group = next((item for item in self.operator_group_catalog if item["id"] == group_id), None)
            if not group:
                raise ValueError(f"未知算子组选项: {raw_group_id}")
            if not self._is_valid_operator_choice(group, choice_id):
                raise ValueError(f"算子组选项 {raw_group_id} 不支持版本 {raw_choice_id}")

            current_value = self._operator_choice(group_id)
            normalized_updates[group_id] = choice_id
            if choice_id != current_value and self._coerce_bool(group.get("requires_restart"), True):
                restart_required = True

        with self.request_state_lock:
            if restart_required and self.active_request_id is not None:
                raise RuntimeError("当前有进行中的推理，请等待完成后再修改需要重启的算子优化项。")

        for group_id, choice_id in normalized_updates.items():
            self.operator_option_values[group_id] = choice_id

        self._persist_operator_option_values()
        if restart_required:
            self._apply_engine_options(restart_running=True)
        return self.operator_options_status()

"""文件说明：推理服务模块，封装 trace 相关的运行时逻辑并被 InferenceService 组合使用。"""

import json
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional


class TraceMixin:
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

    def _is_engine_starting(self) -> bool:
        with self.request_state_lock:
            return bool(self.engine_starting)

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
        if self._is_engine_starting():
            self._stop_process(clear_request_state=False)
            return {
                "accepted": True,
                "request_id": req_id,
                "detail": "已请求停止模型加载。",
            }

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

    def _init_trace(
        self,
        req_id: int,
        prompt: str,
        history_size: int,
        prompt_format: str,
        think_enabled: bool,
        conversation_id: Optional[int] = None,
    ):
        if not self.trace_enabled:
            return
        trace = {
            "request_id": req_id,
            "conversation_id": conversation_id,
            "state": "running",
            "started_at": time.time(),
            "updated_at": time.time(),
            "cancel_requested": False,
            "history_size": int(history_size),
            "prompt_format": prompt_format,
            "think_enabled": bool(think_enabled),
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

        # C++ 进程把推理链路事件写到 stdout；这里按 step 合并，供前端时间线实时展示。
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
                if isinstance(event.get("finish_reason"), str):
                    trace["finish_reason"] = event["finish_reason"]
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
                    step["input_text"] = event["input_text"]
                if isinstance(event.get("tokens_preview"), list):
                    step["tokens_preview"] = [str(item) for item in event["tokens_preview"]]
                if isinstance(event.get("token_count"), (int, float)):
                    step["token_count"] = int(event["token_count"])
                if "truncated" in event:
                    step["truncated"] = bool(event.get("truncated"))
            elif step_id == "encoding":
                if isinstance(event.get("token_ids_preview"), list):
                    values = []
                    for item in event["token_ids_preview"]:
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
                if isinstance(event.get("requested_max_new_tokens"), (int, float)):
                    step["requested_max_new_tokens"] = int(event["requested_max_new_tokens"])
                if isinstance(event.get("effective_max_new_tokens"), (int, float)):
                    step["effective_max_new_tokens"] = int(event["effective_max_new_tokens"])
                if isinstance(event.get("finish_reason"), str):
                    step["finish_reason"] = event["finish_reason"]
                selected_token = event.get("selected_token")
                selected_token_id = event.get("selected_token_id")
                if selected_token is not None or selected_token_id is not None:
                    selected_list = step.setdefault("selected_tokens", [])
                    selected_list.append(
                        {
                            "token": str(selected_token or ""),
                            "token_id": int(selected_token_id) if isinstance(selected_token_id, (int, float)) else None,
                            "index": int(event.get("sample_index")) if isinstance(event.get("sample_index"), (int, float)) else None,
                        }
                    )
                    if len(selected_list) > 256:
                        step["selected_tokens"] = selected_list[-256:]
            elif step_id == "decode":
                if isinstance(event.get("generated_text_preview"), str):
                    step["generated_text_preview"] = event["generated_text_preview"]
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
            if str(raw_line).strip().startswith("[LOAD_PROGRESS]"):
                continue
            self._consume_trace_line(raw_line)

    @staticmethod
    def _append_diag_line(lines: List[str], line: str, limit: int = 8):
        text = str(line or "").strip()
        if not text:
            return
        lines.append(text)
        if len(lines) > limit:
            del lines[:-limit]

    @staticmethod
    def _format_diag_lines(lines: List[str]) -> str:
        if not lines:
            return ""
        joined = " | ".join(str(item).strip() for item in lines if str(item).strip())
        if len(joined) > 600:
            joined = joined[-600:]
        return joined

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

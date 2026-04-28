import json
import os
import queue
import subprocess
import threading
import time
from typing import Dict, List, Optional

from .errors import InferenceCancelledError


class ProcessMixin:
    RESPONSE_CHUNK_MARKER = "[RESPONSE_CHUNK]"

    def _process_env(self) -> Dict[str, str]:
        paged_kv_cache_enabled = self.paged_kv_cache and self._supports_paged_kv_cache()
        optimized_weight_loading = self.optimized_weight_loading and self._supports_optimized_weight_loading()
        operator_env = self.operator_process_env() if hasattr(self, "operator_process_env") else {}
        return {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": os.getenv("CUDA_VISIBLE_DEVICES", "0"),
            "KLLM_TRACE_ENABLED": "1" if self.trace_enabled else "0",
            "KLLM_OPTIMIZED_WEIGHT_LOADING": "1" if optimized_weight_loading else "0",
            "KLLM_PAGED_KV_CACHE": "1" if paged_kv_cache_enabled else "0",
            **operator_env,
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

        with self.request_state_lock:
            self.engine_starting = True

        try:
            if self._is_cancel_requested():
                return

            try:
                self.process = subprocess.Popen(
                    [
                        self.executable,
                        "--serve",
                        self.model_path,
                        self.tokenizer_path,
                        str(self.max_new_tokens),
                        f"{self.temperature:.6f}",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
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
            startup_logs: List[str] = []
            deadline = time.monotonic() + float(self.startup_timeout_seconds)
            ready = False
            while True:
                if self._is_cancel_requested():
                    self._stop_process(clear_request_state=False)
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                ready_line = self._readline_with_timeout(remaining)
                if ready_line is None:
                    break
                text = ready_line.rstrip("\n")
                if text.strip() == "[READY]":
                    ready = True
                    break
                if text.startswith("[LOAD_PROGRESS]"):
                    continue
                if self._consume_trace_line(text):
                    continue
                self._append_diag_line(startup_logs, text)

            if ready:
                return

            if self._is_cancel_requested():
                self._stop_process(clear_request_state=False)
                return

            detail = self._format_diag_lines(startup_logs)
            if self.process and self.process.poll() is not None:
                message = f"✗ 推理进程启动失败（未收到 READY，退出码 {self.process.returncode}）"
                if detail:
                    message += f"，最近日志: {detail}"
                print(message)
            else:
                message = f"✗ 推理引擎启动超时（{self.startup_timeout_seconds}s，未收到 READY）"
                if detail:
                    message += f"，最近日志: {detail}"
                print(message)
            self._stop_process()
        finally:
            with self.request_state_lock:
                self.engine_starting = False

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
        print(f"  temperature: {self.temperature:.3f}")
        print(f"  prompt_format: {self.prompt_format} (effective={self._effective_prompt_format()})")
        print(f"  system_prompt: {self.system_prompt}")
        print(f"  raw_with_history: {self.raw_with_history}")
        print(f"  max_prompt_chars: {self.max_prompt_chars}")
        print(f"  timeout: {self.timeout_seconds}s")
        print(f"  trace_enabled: {self.trace_enabled}")
        print(f"  optimized_weight_loading: {self.optimized_weight_loading}")
        print(f"  paged_kv_cache: {self.paged_kv_cache}")
        print(f"  warmup_on_model_switch: {self.warmup_on_model_switch}")
        if hasattr(self, "operator_process_env"):
            print(f"  operator_env: {self.operator_process_env()}")
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

    def _stop_process(self, clear_request_state: bool = True):
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
            self.engine_starting = False
            if clear_request_state:
                self.active_request_id = None
                self.cancel_requested = False

    def is_ready(self) -> bool:
        return all(
            [
                self.executable,
                self.model_path,
                self.tokenizer_path,
                self.tokenizer_type in {"bpe", "spe"},
                os.path.exists(self.executable) if self.executable else False,
                os.path.exists(self.model_path) if self.model_path else False,
                os.path.exists(self.tokenizer_path) if self.tokenizer_path else False,
            ]
        )

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _extract_response_chunk(self, text: str) -> Optional[str]:
        if not text.startswith(self.RESPONSE_CHUNK_MARKER):
            return None

        payload_text = text[len(self.RESPONSE_CHUNK_MARKER) :].strip()
        if not payload_text:
            return ""

        try:
            payload = json.loads(payload_text)
        except Exception:
            return payload_text

        if isinstance(payload, dict):
            value = payload.get("text", "")
            return value if isinstance(value, str) else str(value)
        if isinstance(payload, str):
            return payload
        return str(payload)

    @staticmethod
    def _response_is_failure_text(text: str) -> bool:
        value = str(text or "")
        return (
            value.startswith("推理超时")
            or value.startswith("推理请求发送失败")
            or value.startswith("推理进程")
            or value.startswith("推理异常")
        )

    def _should_rescue_reasoning_only_answer(self, response: str, think_enabled: bool) -> bool:
        if not think_enabled or not self._supports_reasoning_flow():
            return False
        parsed = self.parse_assistant_response(response)
        return bool(
            parsed.get("think_mode")
            and not parsed.get("answer_complete")
            and parsed.get("reasoning_content")
        )

    def _normalize_rescue_answer_text(self, response: str) -> str:
        parsed = self.parse_assistant_response(response)
        if parsed.get("answer_complete") and parsed.get("answer_content"):
            return str(parsed["answer_content"]).strip()
        if not parsed.get("think_mode"):
            return str(parsed.get("content") or "").strip()
        return ""

    def _mark_answer_rescue_started(self):
        with self.trace_lock:
            if not self.current_trace:
                return
            self.current_trace["answer_rescue"] = True
            self.current_trace["answer_rescue_started_at"] = time.time()
            self.current_trace["updated_at"] = time.time()
            self.last_trace = self.current_trace.copy()

    def _mark_answer_rescue_finished(self, success: bool):
        with self.trace_lock:
            if not self.current_trace:
                return
            self.current_trace["answer_rescue"] = True
            self.current_trace["answer_rescue_success"] = bool(success)
            self.current_trace["answer_rescue_finished_at"] = time.time()
            self.current_trace["updated_at"] = time.time()
            self.last_trace = self.current_trace.copy()

    def _rescue_reasoning_only_response(self, prompt: str, history: List[Dict], response: str) -> str:
        parsed = self.parse_assistant_response(response)
        reasoning_content = str(parsed.get("reasoning_content") or "").strip()
        if not reasoning_content:
            return response

        self._mark_answer_rescue_started()
        rescue_prompt = self._build_prompt(prompt, history or [], think_enabled=False)
        rescue_response = self._generate_with_process(rescue_prompt) if self.is_running() else self._generate_once(rescue_prompt)
        if self._response_is_failure_text(rescue_response):
            print(f"[Inference] qwen reasoning-only rescue failed: {rescue_response}")
            self._mark_answer_rescue_finished(False)
            return response

        answer_text = self._normalize_rescue_answer_text(rescue_response)
        if not answer_text:
            self._mark_answer_rescue_finished(False)
            return response

        combined_response = self._compose_reasoning_response(reasoning_content, answer_text)
        self._mark_answer_rescue_finished(True)
        return combined_response

    def _rescue_reasoning_only_stream(self, prompt: str, history: List[Dict], response: str):
        parsed = self.parse_assistant_response(response)
        reasoning_content = str(parsed.get("reasoning_content") or "").strip()
        if not reasoning_content:
            return response

        self._mark_answer_rescue_started()
        rescue_prompt = self._build_prompt(prompt, history or [], think_enabled=False)
        reasoning_prefix = self._compose_reasoning_response(reasoning_content)
        rescue_response = ""

        if self.is_running():
            for event in self._generate_with_process_stream(rescue_prompt):
                event_type = str(event.get("type") or "").strip().lower()
                if event_type == "delta":
                    rescue_partial = str(event.get("raw_response") or "")
                    rescue_answer = self._normalize_rescue_answer_text(rescue_partial)
                    yield {
                        "type": "delta",
                        "delta": str(event.get("delta") or ""),
                        "raw_response": self._compose_reasoning_response(reasoning_content, rescue_answer),
                    }
                    continue
                if event_type == "done":
                    rescue_response = str(event.get("response") or "")
        else:
            rescue_response = self._generate_once(rescue_prompt)

        if self._response_is_failure_text(rescue_response):
            print(f"[Inference] qwen reasoning-only stream rescue failed: {rescue_response}")
            self._mark_answer_rescue_finished(False)
            return response

        answer_text = self._normalize_rescue_answer_text(rescue_response)
        if not answer_text:
            self._mark_answer_rescue_finished(False)
            return response

        combined_response = self._compose_reasoning_response(reasoning_content, answer_text)
        if combined_response != reasoning_prefix:
            yield {
                "type": "delta",
                "delta": answer_text,
                "raw_response": combined_response,
            }
        self._mark_answer_rescue_finished(True)
        return combined_response

    def generate(
        self,
        prompt: str,
        history: List[Dict] = None,
        think_enabled: bool = True,
        conversation_id: Optional[int] = None,
    ) -> str:
        if not self.is_ready():
            return self._mock_response(prompt)

        req_id = self._next_request_id()
        start_time = time.monotonic()
        safe_history = history or []
        model_prompt = self._build_prompt(prompt, safe_history, think_enabled=think_enabled)
        effective_prompt_format = self._effective_prompt_format()
        print(
            f"[Inference][{req_id}] start: model={self.current_model_id} history={len(safe_history)} "
            f"prompt_chars={len(model_prompt)} max_new_tokens={self.max_new_tokens} "
            f"temperature={self.temperature:.3f} "
            f"prompt_format={effective_prompt_format} think_enabled={bool(think_enabled)}"
        )
        self._init_trace(
            req_id=req_id,
            prompt=prompt,
            history_size=len(safe_history),
            prompt_format=effective_prompt_format,
            think_enabled=bool(think_enabled),
            conversation_id=conversation_id,
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
            response = self._normalize_generated_response(response, think_enabled)

            if self._should_rescue_reasoning_only_answer(response, think_enabled):
                response = self._rescue_reasoning_only_response(prompt, safe_history, response)
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
        failed = self._response_is_failure_text(response)
        self._complete_trace(
            state="error" if failed else "completed",
            response_text=response,
            error=response if failed else "",
            elapsed=elapsed,
        )
        print(f"[Inference][{req_id}] done: elapsed={elapsed:.2f}s response_chars={len(response)}")
        return response

    def generate_stream(
        self,
        prompt: str,
        history: List[Dict] = None,
        think_enabled: bool = True,
        conversation_id: Optional[int] = None,
    ):
        if not self.is_ready():
            response = self._mock_response(prompt)
            yield {
                "type": "delta",
                "delta": response,
                "raw_response": response,
            }
            yield {
                "type": "done",
                "response": response,
            }
            return

        req_id = self._next_request_id()
        start_time = time.monotonic()
        safe_history = history or []
        model_prompt = self._build_prompt(prompt, safe_history, think_enabled=think_enabled)
        effective_prompt_format = self._effective_prompt_format()
        print(
            f"[Inference][{req_id}] start(stream): model={self.current_model_id} history={len(safe_history)} "
            f"prompt_chars={len(model_prompt)} max_new_tokens={self.max_new_tokens} "
            f"temperature={self.temperature:.3f} "
            f"prompt_format={effective_prompt_format} think_enabled={bool(think_enabled)}"
        )
        self._init_trace(
            req_id=req_id,
            prompt=prompt,
            history_size=len(safe_history),
            prompt_format=effective_prompt_format,
            think_enabled=bool(think_enabled),
            conversation_id=conversation_id,
        )
        self._activate_request(req_id)

        response = ""
        try:
            if not self.is_running():
                self._start_engine()

            if self._is_cancel_requested():
                raise InferenceCancelledError("推理已取消")

            if self.is_running():
                stream_failed = False
                try:
                    for event in self._generate_with_process_stream(model_prompt):
                        event = self._normalize_stream_event_response(event, think_enabled)
                        if event.get("type") == "delta":
                            yield event
                        elif event.get("type") == "done":
                            response = str(event.get("response") or "")
                except Exception:
                    stream_failed = True
                    raise
                finally:
                    if stream_failed and not response:
                        response = ""
            else:
                response = self._generate_once(model_prompt)
            response = self._normalize_generated_response(response, think_enabled)

            if self._should_rescue_reasoning_only_answer(response, think_enabled):
                rescue_stream = self._rescue_reasoning_only_stream(prompt, safe_history, response)
                while True:
                    try:
                        rescue_event = next(rescue_stream)
                    except StopIteration as stop:
                        response = str(stop.value or response)
                        break
                    yield rescue_event
        except InferenceCancelledError:
            elapsed = time.monotonic() - start_time
            self._complete_trace(state="cancelled", elapsed=elapsed)
            print(f"[Inference][{req_id}] cancelled(stream): elapsed={elapsed:.2f}s")
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            error_text = f"推理异常: {exc}"
            self._complete_trace(state="error", error=error_text, elapsed=elapsed)
            print(f"[Inference][{req_id}] error(stream): elapsed={elapsed:.2f}s detail={exc}")
            raise
        finally:
            self._clear_active_request(req_id)

        elapsed = time.monotonic() - start_time
        failed = self._response_is_failure_text(response)
        self._complete_trace(
            state="error" if failed else "completed",
            response_text=response,
            error=response if failed else "",
            elapsed=elapsed,
        )
        print(f"[Inference][{req_id}] done(stream): elapsed={elapsed:.2f}s response_chars={len(response)}")
        yield {
            "type": "done",
            "response": response,
        }

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
            diag_lines: List[str] = []
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
                    detail = self._format_diag_lines(diag_lines)
                    time.sleep(0.1)
                    if self.process.poll() is None:
                        self._stop_process()
                        if detail:
                            return f"推理进程输出中断，请检查模型输出编码或进程日志。最近日志: {detail}"
                        return "推理进程输出中断，请检查模型输出编码或进程日志。"
                    self._stop_process()
                    if detail:
                        return f"推理进程已退出，请重试。最近日志: {detail}"
                    return "推理进程已退出，请重试。"

                text = line.rstrip("\n")
                if text.startswith("[LOAD_PROGRESS]"):
                    continue
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
                else:
                    self._append_diag_line(diag_lines, text)

            if cancelled:
                raise InferenceCancelledError("推理已取消")
            response = self._sanitize_response_text("\n".join(response_lines).strip())
            return response if response else "（模型未生成有效回复）"

    def _generate_with_process_stream(self, model_prompt: str):
        with self.lock:
            if not self.is_running() or not self.process:
                yield {
                    "type": "done",
                    "response": "推理进程未运行，请稍后重试。",
                }
                return
            if not self.process.stdin:
                yield {
                    "type": "done",
                    "response": "推理进程 stdin 不可用。",
                }
                return

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
                yield {
                    "type": "done",
                    "response": f"推理请求发送失败: {exc}",
                }
                return

            if self._is_cancel_requested():
                try:
                    self._send_control_command("[CANCEL]")
                except Exception as exc:
                    self._stop_process()
                    yield {
                        "type": "done",
                        "response": f"推理请求发送失败: {exc}",
                    }
                    return

            chunk_parts: List[str] = []
            response_lines: List[str] = []
            diag_lines: List[str] = []
            in_response = False
            cancelled = False
            deadline = time.monotonic() + float(self.timeout_seconds)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._stop_process()
                    yield {
                        "type": "done",
                        "response": f"推理超时（{self.timeout_seconds}s），请减少上下文或降低生成步数。",
                    }
                    return

                line = self._readline_with_timeout(remaining)
                if line is None:
                    detail = self._format_diag_lines(diag_lines)
                    time.sleep(0.1)
                    if self.process.poll() is None:
                        self._stop_process()
                        if detail:
                            yield {
                                "type": "done",
                                "response": f"推理进程输出中断，请检查模型输出编码或进程日志。最近日志: {detail}",
                            }
                            return
                        yield {
                            "type": "done",
                            "response": "推理进程输出中断，请检查模型输出编码或进程日志。",
                        }
                        return
                    self._stop_process()
                    if detail:
                        yield {
                            "type": "done",
                            "response": f"推理进程已退出，请重试。最近日志: {detail}",
                        }
                        return
                    yield {
                        "type": "done",
                        "response": "推理进程已退出，请重试。",
                    }
                    return

                text = line.rstrip("\n")
                if text.startswith("[LOAD_PROGRESS]"):
                    continue
                if self._consume_trace_line(text):
                    continue
                if text == "[CANCELLED]":
                    cancelled = True
                    continue

                chunk = self._extract_response_chunk(text)
                if chunk is not None:
                    chunk_parts.append(chunk)
                    yield {
                        "type": "delta",
                        "delta": chunk,
                        "raw_response": "".join(chunk_parts),
                    }
                    continue

                if text == "[RESPONSE_START]":
                    in_response = True
                    continue
                if text == "[RESPONSE_END]":
                    break
                if in_response:
                    response_lines.append(text)
                else:
                    self._append_diag_line(diag_lines, text)

            if cancelled:
                raise InferenceCancelledError("推理已取消")

            streamed_response = self._sanitize_response_text("".join(chunk_parts).strip())
            buffered_response = self._sanitize_response_text("\n".join(response_lines).strip())
            response = buffered_response or streamed_response
            yield {
                "type": "done",
                "response": response if response else "（模型未生成有效回复）",
            }

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
                        f"{self.temperature:.6f}",
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

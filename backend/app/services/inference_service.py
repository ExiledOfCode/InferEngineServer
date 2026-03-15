import os
import queue
import subprocess
import threading
import time
from typing import Dict, List, Optional

from ..config import settings


class InferenceService:
    """基于 main_qwen.cpp 的推理服务（常驻进程，每次请求触发一次 generate）。"""

    def __init__(self):
        self.engine_path = settings.INFERENCE_ENGINE_PATH
        self.executable: Optional[str] = None
        self.model_path: Optional[str] = None
        self.tokenizer_path: Optional[str] = None
        self.tokenizer_type: Optional[str] = None
        self.model_selection_source: str = "auto"
        self.process: Optional[subprocess.Popen] = None
        self.stdout_queue: Optional[queue.Queue] = None
        self.stdout_reader: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.counter_lock = threading.Lock()
        self.request_counter = 0

        legacy_max_steps = self._read_optional_positive_int("INFERENCE_MAX_STEPS")
        default_max_new_tokens = legacy_max_steps if legacy_max_steps is not None else 128
        self.max_new_tokens = self._read_positive_int("INFERENCE_MAX_NEW_TOKENS", default_max_new_tokens)
        self.timeout_seconds = self._read_positive_int("INFERENCE_TIMEOUT_SECONDS", 180)
        self.startup_timeout_seconds = self._read_positive_int("INFERENCE_STARTUP_TIMEOUT_SECONDS", 900)
        self.max_history_messages = self._read_positive_int("INFERENCE_MAX_HISTORY_MESSAGES", 8)
        self.max_prompt_chars = self._read_positive_int("INFERENCE_MAX_PROMPT_CHARS", 2400)
        self.prompt_format = self._read_prompt_format("INFERENCE_PROMPT_FORMAT", "raw")
        self.raw_with_history = self._read_bool("INFERENCE_RAW_WITH_HISTORY", False)
        if self.max_new_tokens < 8:
            print(f"[WARN] INFERENCE_MAX_NEW_TOKENS={self.max_new_tokens} 偏小，可能导致回复很短。")

        self._detect_model()
        self._start_engine()

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
        return raw if raw in {"raw", "chatml"} else default

    def _next_request_id(self) -> int:
        with self.counter_lock:
            self.request_counter += 1
            return self.request_counter

    def _detect_model(self):
        build_demo_path = os.path.join(self.engine_path, "build", "demo")
        models_root = os.path.join(self.engine_path, "models")
        model_exts = (".bin", ".gguf", ".safetensors")

        def clear_selected_model():
            self.model_path = None
            self.tokenizer_path = None
            self.executable = None
            self.tokenizer_type = None
            self.model_selection_source = "none"

        def tokenizer_type_from_path(path: Optional[str]) -> Optional[str]:
            if not path:
                return None
            lower_path = path.lower()
            if lower_path.endswith(".json"):
                return "bpe"
            if lower_path.endswith(".model"):
                return "spe"
            return None

        def resolve_existing_path(raw_path: str, expect: str) -> Optional[str]:
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

        def find_model_and_tokenizer_in_dir(dir_path: str):
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

        print("=" * 50)
        print("扫描模型文件...")
        candidates: List[Dict[str, str]] = []

        configured_model_dir = str(getattr(settings, "INFERENCE_MODEL_DIR", "") or "").strip()
        configured_model_path = str(getattr(settings, "INFERENCE_MODEL_PATH", "") or "").strip()
        configured_tokenizer_path = str(getattr(settings, "INFERENCE_TOKENIZER_PATH", "") or "").strip()
        has_explicit_config = any([configured_model_dir, configured_model_path, configured_tokenizer_path])

        if has_explicit_config:
            print("  检测到显式模型配置，优先使用 config.py 指定值。")
            print(f"    INFERENCE_MODEL_DIR: {configured_model_dir or '(empty)'}")
            print(f"    INFERENCE_MODEL_PATH: {configured_model_path or '(empty)'}")
            print(f"    INFERENCE_TOKENIZER_PATH: {configured_tokenizer_path or '(empty)'}")

            explicit_dir = None
            explicit_model = None
            explicit_tokenizer = None

            if configured_model_dir:
                explicit_dir = resolve_existing_path(configured_model_dir, "dir")
                if not explicit_dir:
                    print(f"✗ INFERENCE_MODEL_DIR 无效: {configured_model_dir}")
                    clear_selected_model()
                    return

            if configured_model_path:
                explicit_model = resolve_existing_path(configured_model_path, "file")
                if not explicit_model:
                    print(f"✗ INFERENCE_MODEL_PATH 无效: {configured_model_path}")
                    clear_selected_model()
                    return
                lower_model_name = os.path.basename(explicit_model).lower()
                if not lower_model_name.endswith(model_exts):
                    print(f"✗ INFERENCE_MODEL_PATH 不是支持的模型文件: {explicit_model}")
                    print(f"  支持扩展名: {', '.join(model_exts)}")
                    clear_selected_model()
                    return

            if configured_tokenizer_path:
                explicit_tokenizer = resolve_existing_path(configured_tokenizer_path, "file")
                if not explicit_tokenizer:
                    print(f"✗ INFERENCE_TOKENIZER_PATH 无效: {configured_tokenizer_path}")
                    clear_selected_model()
                    return

            selected_dir = explicit_dir

            if not explicit_model:
                infer_dir = explicit_dir
                if not infer_dir and explicit_tokenizer:
                    infer_dir = os.path.dirname(explicit_tokenizer)
                if not infer_dir:
                    print("✗ 请至少配置 INFERENCE_MODEL_DIR 或 INFERENCE_MODEL_PATH")
                    clear_selected_model()
                    return
                explicit_model, detected_tokenizer, detected_tokenizer_type = find_model_and_tokenizer_in_dir(
                    infer_dir
                )
                if not explicit_model:
                    print(f"✗ 指定目录内未找到模型文件: {infer_dir}")
                    clear_selected_model()
                    return
                selected_dir = infer_dir
                if not explicit_tokenizer:
                    explicit_tokenizer = detected_tokenizer
                    explicit_tokenizer_type = detected_tokenizer_type
                else:
                    explicit_tokenizer_type = tokenizer_type_from_path(explicit_tokenizer)
            else:
                explicit_tokenizer_type = tokenizer_type_from_path(explicit_tokenizer)

            if not explicit_tokenizer:
                tokenizer_search_dirs = []
                if explicit_dir:
                    tokenizer_search_dirs.append(explicit_dir)
                tokenizer_search_dirs.append(os.path.dirname(explicit_model))

                for search_dir in tokenizer_search_dirs:
                    _, detected_tokenizer, detected_tokenizer_type = find_model_and_tokenizer_in_dir(search_dir)
                    if detected_tokenizer:
                        explicit_tokenizer = detected_tokenizer
                        explicit_tokenizer_type = detected_tokenizer_type
                        if not selected_dir:
                            selected_dir = search_dir
                        break

            if not explicit_tokenizer:
                print("✗ 无法确定 tokenizer，请配置 INFERENCE_TOKENIZER_PATH")
                clear_selected_model()
                return

            if not explicit_tokenizer_type:
                explicit_tokenizer_type = tokenizer_type_from_path(explicit_tokenizer)

            if not selected_dir:
                selected_dir = os.path.dirname(explicit_model)

            candidates.append(
                {
                    "source": "config",
                    "dir": selected_dir,
                    "model": explicit_model,
                    "tokenizer": explicit_tokenizer,
                    "tokenizer_type": explicit_tokenizer_type or "unknown",
                }
            )
            print("  已根据显式配置定位模型:")
            print(f"    目录: {selected_dir}")
            print(f"    模型: {explicit_model}")
            print(f"    分词器: {explicit_tokenizer} ({explicit_tokenizer_type or 'unknown'})")

        if not has_explicit_config:
            if os.path.exists(models_root):
                for root, _, _ in os.walk(models_root):
                    model_file, tokenizer_file, tokenizer_type = find_model_and_tokenizer_in_dir(root)
                    if model_file and tokenizer_file:
                        candidates.append(
                            {
                                "source": "auto",
                                "dir": root,
                                "model": model_file,
                                "tokenizer": tokenizer_file,
                                "tokenizer_type": tokenizer_type,
                            }
                        )
                        print(f"  找到候选目录: {root}")
                        print(f"    模型: {model_file}")
                        print(f"    分词器: {tokenizer_file} ({tokenizer_type})")

            if not candidates:
                model_file, tokenizer_file, tokenizer_type = find_model_and_tokenizer_in_dir(self.engine_path)
                if model_file and tokenizer_file:
                    candidates.append(
                        {
                            "source": "auto",
                            "dir": self.engine_path,
                            "model": model_file,
                            "tokenizer": tokenizer_file,
                            "tokenizer_type": tokenizer_type,
                        }
                    )
                    print(f"  找到候选目录: {self.engine_path}")
                    print(f"    模型: {model_file}")
                    print(f"    分词器: {tokenizer_file} ({tokenizer_type})")

        if not candidates:
            print("✗ 未找到可用的模型和分词器")
            clear_selected_model()
            return

        def candidate_score(candidate: Dict) -> int:
            if candidate.get("source") == "config":
                return 10**9
            dir_name = os.path.basename(candidate["dir"]).lower()
            score = 0
            if "qwen" in dir_name:
                score += 100
            if candidate["tokenizer_type"] == "bpe":
                score += 50
            if "llama" in dir_name:
                score += 20
            model_name = os.path.basename(candidate["model"]).lower()
            if model_name.endswith(".bin"):
                score += 30
            elif model_name.endswith(".safetensors"):
                score -= 10
            return score

        candidates.sort(key=candidate_score, reverse=True)
        selected = candidates[0]

        self.model_path = selected["model"]
        self.tokenizer_path = selected["tokenizer"]
        self.tokenizer_type = selected["tokenizer_type"]
        self.model_selection_source = selected.get("source", "auto")

        print("=" * 50)
        print("已选择模型目录:")
        print(f"  来源: {'显式配置' if self.model_selection_source == 'config' else '自动扫描'}")
        print(f"  目录: {selected['dir']}")
        print(f"  模型: {self.model_path}")
        print(f"  分词器: {self.tokenizer_path}")
        print(f"  类型: {self.tokenizer_type}")

        qwen_single_shot = os.path.join(build_demo_path, "qwen_infer")
        if self.tokenizer_type != "bpe":
            print("✗ 当前仅支持 BPE/Qwen tokenizer 的 main_qwen 推理模式")
            print("  请使用 Qwen 模型 + tokenizer.json")
            self.executable = None
            return
        if not os.path.exists(qwen_single_shot):
            print("✗ 未找到 qwen_infer 可执行文件")
            print(f"  期望路径: {qwen_single_shot}")
            print("  请先编译: cmake --build build --target qwen_infer -j$(nproc)")
            self.executable = None
            return

        self.executable = qwen_single_shot
        print("✓ 使用推理引擎: qwen_infer (main_qwen)")

    def _start_engine(self):
        if not self.is_ready():
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
            print(f"✗ 推理进程启动失败: {exc}")
            self.process = None
            return

        self._start_stdout_reader()
        ready_line = self._readline_with_timeout(self.startup_timeout_seconds)
        if ready_line is None:
            print(f"✗ 推理引擎启动超时（{self.startup_timeout_seconds}s，未收到 READY）")
            self._stop_process()
            return
        if ready_line.strip() != "[READY]":
            print(f"✗ 推理引擎启动异常，收到: {ready_line.strip()}")
            self._stop_process()
            return

        print("=" * 50)
        print("推理模式: 常驻进程（每条消息触发一次 generate）")
        print(f"  可执行文件: {self.executable}")
        print(f"  model_selection: {self.model_selection_source}")
        print(f"  模型: {os.path.basename(self.model_path)}")
        print(f"  分词器: {os.path.basename(self.tokenizer_path)}")
        print(f"  max_new_tokens: {self.max_new_tokens}")
        print(f"  prompt_format: {self.prompt_format}")
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

    def generate(self, prompt: str, history: List[Dict] = None) -> str:
        if not self.is_ready():
            return self._mock_response(prompt)

        req_id = self._next_request_id()
        start_time = time.monotonic()
        safe_history = history or []
        model_prompt = self._build_prompt(prompt, safe_history)
        print(
            f"[Inference][{req_id}] start: history={len(safe_history)} "
            f"prompt_chars={len(model_prompt)} max_new_tokens={self.max_new_tokens}"
        )

        if not self.is_running():
            self._start_engine()

        if self.is_running():
            response = self._generate_with_process(model_prompt)
        else:
            # 兜底：进程模式不可用时仍可单次调用
            response = self._generate_once(model_prompt)

        elapsed = time.monotonic() - start_time
        print(f"[Inference][{req_id}] done: elapsed={elapsed:.2f}s response_chars={len(response)}")
        return response

    def _build_prompt(self, prompt: str, history: List[Dict]) -> str:
        if self.prompt_format == "raw":
            return self._build_raw_prompt(prompt, history)
        return self._build_chatml_prompt(prompt, history)

    def _build_raw_prompt(self, prompt: str, history: List[Dict]) -> str:
        clean_prompt = (prompt or "").strip()
        if not self.raw_with_history:
            return clean_prompt

        # raw 模式下可选拼接少量对话历史，格式尽量接近自然文本
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
            messages.insert(0, {"role": "system", "content": "You are a helpful assistant."})

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
        with self.lock:
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
            if line.startswith("steps:") or line.startswith("duration:") or line.startswith("steps/s:"):
                continue
            lines.append(raw_line)
        return "\n".join(lines).strip()

    @staticmethod
    def _sanitize_response_text(text: str) -> str:
        """压制模型连续重复刷屏输出。"""
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
            "engine_path": self.engine_path,
            "executable": self.executable,
            "model_selection_source": self.model_selection_source,
            "model_path": self.model_path,
            "tokenizer_path": self.tokenizer_path,
            "tokenizer_type": self.tokenizer_type,
            "configured_model_dir": settings.INFERENCE_MODEL_DIR,
            "configured_model_path": settings.INFERENCE_MODEL_PATH,
            "configured_tokenizer_path": settings.INFERENCE_TOKENIZER_PATH,
            "max_new_tokens": self.max_new_tokens,
            "prompt_format": self.prompt_format,
            "raw_with_history": self.raw_with_history,
            "max_history_messages": self.max_history_messages,
            "max_prompt_chars": self.max_prompt_chars,
            "timeout_seconds": self.timeout_seconds,
            "startup_timeout_seconds": self.startup_timeout_seconds,
            "pid": self.process.pid if self.process and self.is_running() else None,
        }

    def _mock_response(self, prompt: str) -> str:
        return f"""推理引擎未就绪。

你的问题是: {prompt}

请检查:
- 可执行文件(qwen_infer): {'✓' if self.executable else '❌ 未找到'}
- 模型文件: {'✓' if self.model_path else '❌ 未找到'}
- 分词器(tokenizer.json): {'✓' if self.tokenizer_path else '❌ 未找到'}
"""

    def clear_history(self):
        """当前实现按请求传完整 history，无进程内会话态。"""
        return None

    def shutdown(self):
        self._stop_process()


# 全局单例
inference_service = InferenceService()

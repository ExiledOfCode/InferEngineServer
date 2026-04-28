import os
from typing import Dict, List, Optional


class PromptMixin:
    REASONING_MODEL_FAMILIES = {"qwen3"}

    def _supports_reasoning_flow(self) -> bool:
        explicit = getattr(self, "current_model_supports_reasoning", None)
        if explicit is not None:
            return bool(explicit)
        return self.current_model_family in self.REASONING_MODEL_FAMILIES

    def _uses_chatml_reasoning_prefix(self, think_enabled: bool) -> bool:
        return (
            bool(think_enabled)
            and self._supports_reasoning_flow()
            and self._effective_prompt_format() == "chatml"
        )

    def _forced_assistant_response_prefix(self, think_enabled: bool) -> str:
        if self._uses_chatml_reasoning_prefix(think_enabled):
            return f"{self.THINK_OPEN_TAG}\n"
        return ""

    def _normalize_generated_response(self, text: str, think_enabled: bool) -> str:
        value = str(text or "")
        prefix = self._forced_assistant_response_prefix(think_enabled)
        if not prefix:
            return value
        if self._strip_response_prefix(value).startswith(self.THINK_OPEN_TAG):
            return value
        return f"{prefix}{value}"

    def _normalize_stream_event_response(self, event: Dict, think_enabled: bool) -> Dict:
        event_type = str(event.get("type") or "").strip().lower()
        if event_type == "delta":
            normalized = dict(event)
            normalized["raw_response"] = self._normalize_generated_response(
                str(event.get("raw_response") or ""),
                think_enabled,
            )
            return normalized
        if event_type == "done":
            normalized = dict(event)
            normalized["response"] = self._normalize_generated_response(
                str(event.get("response") or ""),
                think_enabled,
            )
            return normalized
        return event

    @staticmethod
    def _strip_visible_end_markers(text: str) -> str:
        value = str(text or "")
        end_markers = (
            "<|im_end|>",
            "<|endoftext|>",
            "<|end|>",
            "</s>",
            "<|eot_id|>",
            "<|end_of_text|>",
            "<｜end▁of▁sentence｜>",
        )
        for marker in end_markers:
            marker_pos = value.find(marker)
            if marker_pos != -1:
                value = value[:marker_pos]
        return value

    @staticmethod
    def _strip_response_prefix(text: str) -> str:
        value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        value = value.lstrip()
        while value.startswith(":") or value.startswith("："):
            value = value[1:].lstrip()
        return value.strip()

    @classmethod
    def parse_assistant_response(cls, text: str) -> Dict[str, Optional[str] | bool]:
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
        if reasoning_content:
            reasoning_content = cls._sanitize_reasoning_text(reasoning_content) or None
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
    def parse_streaming_assistant_response(cls, text: str) -> Dict[str, Optional[str] | bool]:
        raw_content = cls._strip_response_prefix(
            cls._strip_visible_end_markers(cls._sanitize_response_text(text))
        )
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
                "answer_complete": False,
            }

        after_open = raw_content[think_start + len(cls.THINK_OPEN_TAG) :]
        think_end = after_open.find(cls.THINK_CLOSE_TAG)
        if think_end == -1:
            reasoning_content = after_open.strip() or None
            if reasoning_content:
                reasoning_content = cls._sanitize_reasoning_text(reasoning_content) or None
            return {
                "raw_content": raw_content,
                "content": "",
                "reasoning_content": reasoning_content,
                "answer_content": None,
                "think_mode": True,
                "answer_complete": False,
            }

        reasoning_content = after_open[:think_end].strip() or None
        if reasoning_content:
            reasoning_content = cls._sanitize_reasoning_text(reasoning_content) or None
        answer_content = cls._strip_response_prefix(
            cls._strip_visible_end_markers(after_open[think_end + len(cls.THINK_CLOSE_TAG) :])
        ) or None
        return {
            "raw_content": raw_content,
            "content": answer_content or "",
            "reasoning_content": reasoning_content,
            "answer_content": answer_content,
            "think_mode": True,
            "answer_complete": bool(answer_content),
        }

    @staticmethod
    def _sanitize_reasoning_text(text: str) -> str:
        if not text:
            return ""
        kept: List[str] = []
        for raw_line in str(text).replace("\r\n", "\n").replace("\r", "\n").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if lower.startswith("utterance:"):
                continue
            kept.append(raw_line.strip())
        return "\n".join(kept).strip()

    @classmethod
    def _compose_reasoning_response(cls, reasoning_content: Optional[str], answer_content: str = "") -> str:
        reasoning_text = str(reasoning_content or "").strip()
        answer_text = cls._strip_response_prefix(
            cls._strip_visible_end_markers(cls._sanitize_response_text(answer_content))
        )

        if reasoning_text:
            body = f"{cls.THINK_OPEN_TAG}\n{reasoning_text}\n{cls.THINK_CLOSE_TAG}"
        else:
            body = f"{cls.THINK_OPEN_TAG}\n\n{cls.THINK_CLOSE_TAG}"

        if answer_text:
            return f"{body}\n\n{answer_text}".strip()
        return body.strip()

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

    def _effective_prompt_format(self) -> str:
        if self.current_model_family == "deepseek_qwen" and self.prompt_format != "raw":
            return "deepseek"

        if self.prompt_format in {"raw", "chatml", "deepseek", "llama3", "tinyllama"}:
            return self.prompt_format

        if self.current_model_family == "llama3":
            return "llama3"
        if self.current_model_family == "tinyllama":
            return "tinyllama"
        if self.current_model_family == "smollm":
            return "chatml"

        if self.current_model_family in {"llama", "deepseek_llama"}:
            return "raw"

        model_hint = " ".join(
            [
                self.current_model_family or "",
                self.current_model_name or "",
                os.path.basename(self.model_path or ""),
                os.path.basename(os.path.dirname(self.model_path or "")),
            ]
        ).lower()
        if any(key in model_hint for key in ("qwen", "deepseek")):
            return "chatml"
        if any(key in model_hint for key in ("instruct", "chat")):
            return "chatml"
        return "raw"

    def _build_prompt(self, prompt: str, history: List[Dict], think_enabled: bool = True) -> str:
        effective_prompt_format = self._effective_prompt_format()
        if effective_prompt_format == "raw":
            return self._build_raw_prompt(prompt, history)
        if effective_prompt_format == "llama3":
            return self._build_llama3_prompt(prompt, history)
        if effective_prompt_format == "tinyllama":
            return self._build_tinyllama_prompt(prompt, history)
        if effective_prompt_format == "deepseek":
            return self._build_deepseek_prompt(prompt, history, think_enabled=think_enabled)
        return self._build_chatml_prompt(prompt, history, think_enabled=think_enabled)

    def _collect_structured_messages(
        self,
        prompt: str,
        history: List[Dict],
        default_system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
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

        if default_system_prompt and not any(message["role"] == "system" for message in messages):
            messages.insert(0, {"role": "system", "content": default_system_prompt})

        return self._truncate_messages_by_chars(messages)

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

    def _build_chatml_prompt(self, prompt: str, history: List[Dict], think_enabled: bool = True) -> str:
        messages = self._collect_structured_messages(prompt, history, default_system_prompt=self.system_prompt)

        parts = []
        for message in messages:
            parts.append(f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>")
        if self._uses_chatml_reasoning_prefix(think_enabled):
            parts.append("<|im_start|>assistant\n<think>\n")
        elif self._supports_reasoning_flow() and not think_enabled:
            parts.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
        else:
            parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def _build_llama3_prompt(self, prompt: str, history: List[Dict]) -> str:
        messages = self._collect_structured_messages(prompt, history, default_system_prompt=self.system_prompt)
        parts = ["<|begin_of_text|>"]
        for message in messages:
            parts.append(
                f"<|start_header_id|>{message['role']}<|end_header_id|>\n\n"
                f"{message['content']}<|eot_id|>"
            )
        parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
        return "".join(parts)

    def _build_tinyllama_prompt(self, prompt: str, history: List[Dict]) -> str:
        messages = self._collect_structured_messages(prompt, history, default_system_prompt=self.system_prompt)
        role_tokens = {
            "system": "<|system|>",
            "user": "<|user|>",
            "assistant": "<|assistant|>",
        }
        parts = []
        for message in messages:
            role_token = role_tokens.get(message["role"])
            if not role_token:
                continue
            parts.append(f"{role_token}\n{message['content']}</s>")
        parts.append("<|assistant|>")
        return "\n".join(parts)

    def _build_deepseek_prompt(self, prompt: str, history: List[Dict], think_enabled: bool = True) -> str:
        messages = self._collect_structured_messages(prompt, history, default_system_prompt=self.system_prompt)
        system_text = next(
            (message["content"] for message in messages if message["role"] == "system"),
            self.system_prompt,
        )

        parts = ["<｜begin▁of▁sentence｜>", system_text]
        for message in messages:
            if message["role"] == "system":
                continue
            if message["role"] == "user":
                parts.append(f"<｜User｜>{message['content']}")
            elif message["role"] == "assistant":
                parts.append(f"<｜Assistant｜>{message['content']}<｜end▁of▁sentence｜>")

        if think_enabled:
            parts.append("<｜Assistant｜><think>\n")
        else:
            parts.append("<｜Assistant｜>")
        return "".join(parts)

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
            if line.startswith("[LOAD_PROGRESS]"):
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
        prev_key = ""
        same_run = 0
        for line in lines:
            norm = line.strip()
            key = norm.replace("<think>", "").replace("</think>", "").strip()

            if key and key == prev_key and len(key) <= 200:
                same_run += 1
                if same_run >= 2 and len(key) <= 32:
                    if kept and kept[-1].strip().replace("<think>", "").replace("</think>", "").strip() == key:
                        kept.pop()
                    break
                if same_run >= 3:
                    continue
            else:
                prev_key = key
                same_run = 1

            if key.lower().startswith("utterance:"):
                if "<think>" in norm.lower() or "</think>" in norm.lower():
                    kept.append(line)
                    continue
                recent = [
                    item.strip().replace("<think>", "").replace("</think>", "").strip()
                    for item in kept[-2:]
                ]
                if key in recent:
                    continue

            kept.append(line)

        return "\n".join(kept).strip()

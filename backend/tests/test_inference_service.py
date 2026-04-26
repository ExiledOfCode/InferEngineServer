import json
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

from app.config import settings
from app.services.inference import InferenceService


class InferenceServiceTestCase(unittest.TestCase):
    def setUp(self):
        self._settings_backup = {}
        self._env_patch = patch.dict(
            os.environ,
            {
                "INFERENCE_MAX_STEPS": "",
                "INFERENCE_MAX_NEW_TOKENS": "",
                "INFERENCE_TEMPERATURE": "",
                "INFERENCE_TIMEOUT_SECONDS": "10",
                "INFERENCE_STARTUP_TIMEOUT_SECONDS": "10",
                "INFERENCE_MAX_HISTORY_MESSAGES": "8",
                "INFERENCE_MAX_PROMPT_CHARS": "512",
                "INFERENCE_PROMPT_FORMAT": "auto",
                "INFERENCE_RAW_WITH_HISTORY": "false",
                "INFERENCE_SYSTEM_PROMPT": "你是测试助手。",
                "INFERENCE_EAGER_START": "false",
            },
            clear=False,
        )
        self._env_patch.start()

    def tearDown(self):
        self._restore_settings()
        self._env_patch.stop()

    def _override_settings(self, **overrides):
        for key, value in overrides.items():
            if key not in self._settings_backup:
                self._settings_backup[key] = getattr(settings, key)
            setattr(settings, key, value)

    def _restore_settings(self):
        for key, value in self._settings_backup.items():
            setattr(settings, key, value)
        self._settings_backup.clear()

    @staticmethod
    def _write_text(path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    @staticmethod
    def _write_model(path, seq_len=256):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        header = struct.pack("<iiiiiii", 1, 2, 3, 4, 5, 6, seq_len)
        with open(path, "wb") as fh:
            fh.write(header)
            fh.write(b"\0" * (64 - len(header)))

    def _build_service(self, workdir):
        engine_dir = os.path.join(workdir, "engine")
        ready_dir = os.path.join(engine_dir, "models", "ready-model")
        broken_dir = os.path.join(engine_dir, "models", "broken-model")
        runtime_path = os.path.join(workdir, "runtime", "inference_options.json")
        operator_runtime_path = os.path.join(workdir, "runtime", "operator_options.json")

        ready_executable = os.path.join(engine_dir, "build", "demo", "qwen3_infer")
        broken_executable = os.path.join(engine_dir, "build", "demo", "qwen_infer")
        self._write_text(ready_executable, "#!/bin/sh\nexit 0\n")
        self._write_text(broken_executable, "#!/bin/sh\nexit 0\n")
        os.chmod(ready_executable, 0o755)
        os.chmod(broken_executable, 0o755)

        ready_model = os.path.join(ready_dir, "ready-model.bin")
        ready_tokenizer = os.path.join(ready_dir, "tokenizer.json")
        broken_model = os.path.join(broken_dir, "broken-model.bin")
        self._write_model(ready_model, seq_len=256)
        self._write_model(broken_model, seq_len=512)
        self._write_text(ready_tokenizer, "{}")

        self._write_text(
            runtime_path,
            json.dumps(
                {
                    "options": {
                        "trace_enabled": False,
                        "warmup_on_model_switch": False,
                    },
                    "settings": {
                        "max_new_tokens": 96,
                        "temperature": 0.7,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        self._write_text(
            operator_runtime_path,
            json.dumps(
                {
                    "operators": {
                        "matmul_impl": "cublas",
                        "rmsnorm_impl": "lab_warp_reduce",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        models = [
            {
                "id": "broken-model",
                "name": "Broken Model",
                "family": "qwen2",
                "model_dir": broken_dir,
                "model_path": broken_model,
                "tokenizer_path": os.path.join(broken_dir, "tokenizer.json"),
                "executable_path": broken_executable,
                "prompt_format": "chatml",
            },
            {
                "id": "ready-model",
                "name": "Ready Model",
                "family": "qwen3",
                "model_dir": ready_dir,
                "model_path": ready_model,
                "tokenizer_path": ready_tokenizer,
                "executable_path": ready_executable,
                "prompt_format": "chatml",
                "max_new_tokens": 128,
            },
        ]
        options = [
            {
                "id": "warmup_on_model_switch",
                "name": "切模预热",
                "description": "测试环境关闭自动预热。",
                "default_enabled": False,
                "requires_restart": False,
            }
        ]
        operator_options = [
            {
                "id": "matmul_impl",
                "name": "GEMM / MatMul",
                "description": "测试矩阵乘实现切换。",
                "env_var": "KLLM_OP_MATMUL_IMPL",
                "default_selected": "kuiper_cuda",
                "requires_restart": True,
                "choices": [
                    {
                        "id": "kuiper_cuda",
                        "name": "Kuiper CUDA",
                        "description": "默认实现。",
                        "supported": True,
                    },
                    {
                        "id": "cublas",
                        "name": "cuBLAS",
                        "description": "测试实现。",
                        "supported": True,
                    },
                ],
            },
            {
                "id": "rmsnorm_impl",
                "name": "RMSNorm",
                "description": "测试 RMSNorm 实现切换。",
                "env_var": "KLLM_OP_RMSNORM_IMPL",
                "default_selected": "kuiper_cuda",
                "requires_restart": True,
                "choices": [
                    {
                        "id": "kuiper_cuda",
                        "name": "Kuiper CUDA",
                        "description": "默认实现。",
                        "supported": True,
                    },
                    {
                        "id": "lab_warp_reduce",
                        "name": "Lab Warp Reduce",
                        "description": "实验实现。",
                        "supported": True,
                    },
                ],
            },
        ]

        self._override_settings(
            INFERENCE_ENGINE_PATH=engine_dir,
            INFERENCE_MODEL_DIR="",
            INFERENCE_MODEL_PATH="",
            INFERENCE_TOKENIZER_PATH="",
            INFERENCE_DEFAULT_MODEL_ID="broken-model",
            INFERENCE_RUNTIME_OPTIONS_PATH=runtime_path,
            INFERENCE_ENGINE_OPTIONS_JSON=json.dumps(options, ensure_ascii=False, indent=2),
            INFERENCE_OPERATOR_OPTIONS_PATH=operator_runtime_path,
            INFERENCE_OPERATOR_OPTIONS_JSON=json.dumps(operator_options, ensure_ascii=False, indent=2),
            INFERENCE_MODELS_JSON=json.dumps(models, ensure_ascii=False, indent=2),
        )
        return InferenceService(), runtime_path, operator_runtime_path

    def test_parse_assistant_response_extracts_reasoning_and_answer(self):
        parsed = InferenceService.parse_assistant_response(
            "<think>\n第一步\nutterance: hidden\n</think>\n：最终答案"
        )

        self.assertTrue(parsed["think_mode"])
        self.assertTrue(parsed["answer_complete"])
        self.assertEqual(parsed["reasoning_content"], "第一步")
        self.assertEqual(parsed["content"], "最终答案")
        self.assertEqual(parsed["answer_content"], "最终答案")

    def test_parse_streaming_assistant_response_keeps_thinking_and_partial_answer_separate(self):
        thinking = InferenceService.parse_streaming_assistant_response("<think>\n先分析问题")
        answering = InferenceService.parse_streaming_assistant_response(
            "<think>\n先分析问题\n</think>\n：部分答案"
        )

        self.assertTrue(thinking["think_mode"])
        self.assertEqual(thinking["reasoning_content"], "先分析问题")
        self.assertEqual(thinking["content"], "")
        self.assertFalse(thinking["answer_complete"])

        self.assertTrue(answering["think_mode"])
        self.assertEqual(answering["reasoning_content"], "先分析问题")
        self.assertEqual(answering["content"], "部分答案")
        self.assertEqual(answering["answer_content"], "部分答案")

    def test_default_runtime_options_path_points_to_backend_runtime_directory(self):
        service = InferenceService()
        expected = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "runtime", "inference_options.json")
        )
        self.assertEqual(service.runtime_options_path, expected)
        service.shutdown()

    def test_chatml_prompt_ignores_incomplete_assistant_thinking(self):
        with tempfile.TemporaryDirectory() as workdir:
            service, _, _ = self._build_service(workdir)
            history = [
                {"role": "assistant", "content": "<think>不应进入历史"},
                {"role": "user", "content": "上一轮问题"},
                {"role": "assistant", "content": "上一轮答案"},
            ]

            prompt = service._build_chatml_prompt("新的问题", history, think_enabled=False)

            self.assertIn("上一轮问题", prompt)
            self.assertIn("上一轮答案", prompt)
            self.assertNotIn("不应进入历史", prompt)
            self.assertIn("<|im_start|>assistant\n<think>\n\n</think>\n\n", prompt)

    def test_model_registry_prefers_ready_model_and_persists_runtime_updates(self):
        with tempfile.TemporaryDirectory() as workdir:
            service, runtime_path, operator_runtime_path = self._build_service(workdir)

            self.assertEqual(service.current_model_id, "ready_model")
            self.assertFalse(service.trace_enabled)
            self.assertFalse(service.warmup_on_model_switch)
            self.assertEqual(service.max_new_tokens, 96)
            self.assertAlmostEqual(service.temperature, 0.7, places=6)
            self.assertEqual(service._operator_choice("matmul_impl"), "cublas")
            self.assertEqual(service._operator_choice("rmsnorm_impl"), "lab_warp_reduce")

            listed = {item["id"]: item for item in service.list_models()}
            self.assertFalse(listed["broken_model"]["ready"])
            self.assertTrue(listed["ready_model"]["ready"])

            service.update_engine_options({"trace_enabled": True})
            service.update_generation_settings(max_new_tokens=120, temperature=1.1)
            service.update_operator_options({"matmul_impl": "kuiper_cuda"})

            with open(runtime_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            with open(operator_runtime_path, "r", encoding="utf-8") as fh:
                operator_payload = json.load(fh)

            self.assertTrue(payload["options"]["trace_enabled"])
            self.assertFalse(payload["options"]["warmup_on_model_switch"])
            self.assertEqual(payload["settings"]["max_new_tokens"], 120)
            self.assertAlmostEqual(payload["settings"]["temperature"], 1.1, places=6)
            self.assertEqual(operator_payload["operators"]["matmul_impl"], "kuiper_cuda")
            self.assertEqual(operator_payload["operators"]["rmsnorm_impl"], "lab_warp_reduce")
            process_env = service._process_env()
            self.assertEqual(process_env["KLLM_OP_MATMUL_IMPL"], "kuiper_cuda")
            self.assertEqual(process_env["KLLM_OP_RMSNORM_IMPL"], "lab_warp_reduce")

    def test_qwen_reasoning_only_response_triggers_sync_answer_rescue(self):
        with tempfile.TemporaryDirectory() as workdir:
            service, _, _ = self._build_service(workdir)
            prompts = []

            def fake_generate(prompt):
                prompts.append(prompt)
                if len(prompts) == 1:
                    return "<think>\n先分析问题"
                return "最终答案"

            with patch.object(service, "_start_engine", return_value=None), patch.object(
                service, "is_running", return_value=True
            ), patch.object(service, "_generate_with_process", side_effect=fake_generate):
                response = service.generate("新的问题", history=[], think_enabled=True)

            self.assertEqual(len(prompts), 2)
            self.assertTrue(prompts[1].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"))
            self.assertIn("<think>", response)
            self.assertIn("</think>", response)
            self.assertIn("最终答案", response)

    def test_qwen_reasoning_only_stream_triggers_answer_rescue(self):
        with tempfile.TemporaryDirectory() as workdir:
            service, _, _ = self._build_service(workdir)
            prompts = []

            def fake_stream(prompt):
                prompts.append(prompt)
                if len(prompts) == 1:
                    yield {
                        "type": "delta",
                        "delta": "<think>",
                        "raw_response": "<think>",
                    }
                    yield {
                        "type": "delta",
                        "delta": "\n先分析问题",
                        "raw_response": "<think>\n先分析问题",
                    }
                    yield {
                        "type": "done",
                        "response": "<think>\n先分析问题",
                    }
                    return

                yield {
                    "type": "delta",
                    "delta": "最终",
                    "raw_response": "最终",
                }
                yield {
                    "type": "done",
                    "response": "最终答案",
                }

            with patch.object(service, "_start_engine", return_value=None), patch.object(
                service, "is_running", return_value=True
            ), patch.object(service, "_generate_with_process_stream", side_effect=fake_stream):
                events = list(service.generate_stream("新的问题", history=[], think_enabled=True))

            self.assertEqual(len(prompts), 2)
            self.assertTrue(prompts[1].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"))
            delta_events = [event for event in events if event.get("type") == "delta"]
            done_event = events[-1]

            self.assertGreaterEqual(len(delta_events), 3)
            self.assertIn("最终答案", done_event["response"])
            self.assertIn("</think>", done_event["response"])
            self.assertIn("最终答案", delta_events[-1]["raw_response"])

if __name__ == "__main__":
    unittest.main()

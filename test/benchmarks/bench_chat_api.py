#!/usr/bin/env python3
"""文件说明：HTTP 基准测试脚本，压测 bench_chat_api 对应的服务端接口。"""

import argparse

from common_http import DEFAULT_BASE_URL, http_json, print_artifacts, resolve_token, write_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark multi-turn chat API on the server inference path.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--title", default="benchmark-chat")
    parser.add_argument("--prompt", default="请用一句话说明什么是质数。")
    parser.add_argument("--think-enabled", action="store_true", default=False)
    parser.add_argument("--keep-conversation", action="store_true")
    args = parser.parse_args()

    token = resolve_token(args.base_url, args.token, args.username, args.password, timeout=args.timeout)
    rows = []

    create_result = http_json("POST", args.base_url, "/conversations", token=token, body={"title": args.title}, timeout=30)
    conversation_id = None
    if isinstance(create_result.get("payload"), dict):
        conversation_id = create_result["payload"].get("id")
    rows.append(
        {
            "case": "create_conversation",
            "index": 0,
            "status": create_result["status"],
            "ok": create_result["ok"] and conversation_id is not None,
            "latency_sec": create_result["latency_sec"],
            "conversation_id": conversation_id,
            "error": create_result["error"],
        }
    )
    if not conversation_id:
        paths = write_artifacts("server_chat_api", rows, {"base_url": args.base_url, "repeat": args.repeat})
        print_artifacts(paths)
        return 1

    for index in range(args.repeat):
        prompt = args.prompt if args.repeat == 1 else f"{args.prompt}\n这是第 {index + 1} 轮。"
        result = http_json(
            "POST",
            args.base_url,
            f"/conversations/{conversation_id}/messages",
            token=token,
            body={"content": prompt, "think_enabled": args.think_enabled},
            timeout=args.timeout,
        )
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        trace = payload.get("inference_trace") if isinstance(payload.get("inference_trace"), dict) else {}
        row = {
            "case": "send_message",
            "index": index,
            "conversation_id": conversation_id,
            "message_id": payload.get("id"),
            "status": result["status"],
            "ok": result["ok"],
            "latency_sec": result["latency_sec"],
            "prompt_chars": len(prompt),
            "response_chars": len(str(payload.get("content") or "")),
            "reasoning_chars": len(str(payload.get("reasoning_content") or "")),
            "trace_state": trace.get("state"),
            "trace_step_count": len(trace.get("steps") or []) if isinstance(trace.get("steps"), list) else None,
            "error": result["error"],
        }
        rows.append(row)
        print(
            f"send_message index={index} status={row['status']} latency={row['latency_sec']:.3f}s "
            f"chars={row['response_chars']}"
        )

    if not args.keep_conversation:
        result = http_json("DELETE", args.base_url, f"/conversations/{conversation_id}", token=token, timeout=30)
        rows.append(
            {
                "case": "delete_conversation",
                "index": 0,
                "conversation_id": conversation_id,
                "status": result["status"],
                "ok": result["ok"],
                "latency_sec": result["latency_sec"],
                "error": result["error"],
            }
        )

    paths = write_artifacts(
        "server_chat_api",
        rows,
        {
            "base_url": args.base_url,
            "repeat": args.repeat,
            "think_enabled": args.think_enabled,
            "keep_conversation": args.keep_conversation,
        },
    )
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

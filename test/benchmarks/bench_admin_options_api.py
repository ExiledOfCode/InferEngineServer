#!/usr/bin/env python3
"""文件说明：HTTP 基准测试脚本，压测 bench_admin_options_api 对应的服务端接口。"""

import argparse

from common_http import DEFAULT_BASE_URL, http_json, print_artifacts, resolve_token, write_artifacts


def options_fields(payload):
    if not isinstance(payload, dict):
        return {}
    options = payload.get("options") if isinstance(payload.get("options"), list) else []
    return {
        "current_model_id": payload.get("current_model_id"),
        "ready": payload.get("ready"),
        "running": payload.get("running"),
        "max_new_tokens": payload.get("max_new_tokens"),
        "temperature": payload.get("temperature"),
        "trace_enabled": payload.get("trace_enabled"),
        "warmup_on_model_switch": payload.get("warmup_on_model_switch"),
        "option_count": len(options),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark admin inference options API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--write-check",
        action="store_true",
        help="PUT the current max_new_tokens/temperature back once to verify write path without changing values.",
    )
    args = parser.parse_args()

    token = resolve_token(args.base_url, args.token, args.username, args.password, timeout=args.timeout)
    rows = []
    latest_payload = None
    for index in range(args.repeat):
        result = http_json("GET", args.base_url, "/admin/inference/options", token=token, timeout=args.timeout)
        latest_payload = result.get("payload") if result["ok"] else latest_payload
        row = {
            "case": "admin_options_get",
            "index": index,
            "status": result["status"],
            "ok": result["ok"],
            "latency_sec": result["latency_sec"],
            "error": result["error"],
        }
        row.update(options_fields(result.get("payload")))
        rows.append(row)
        print(f"admin_options_get index={index} status={row['status']} latency={row['latency_sec']:.4f}s")

    if args.write_check and isinstance(latest_payload, dict):
        body = {
            "options": {},
            "max_new_tokens": latest_payload.get("max_new_tokens"),
            "temperature": latest_payload.get("temperature"),
        }
        result = http_json("PUT", args.base_url, "/admin/inference/options", token=token, body=body, timeout=args.timeout)
        row = {
            "case": "admin_options_put_same_values",
            "index": 0,
            "status": result["status"],
            "ok": result["ok"],
            "latency_sec": result["latency_sec"],
            "error": result["error"],
        }
        row.update(options_fields(result.get("payload")))
        rows.append(row)
        print(f"admin_options_put_same_values status={row['status']} latency={row['latency_sec']:.4f}s")

    paths = write_artifacts(
        "server_admin_options_api",
        rows,
        {
            "base_url": args.base_url,
            "repeat": args.repeat,
            "write_check": args.write_check,
        },
    )
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

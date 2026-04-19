#!/usr/bin/env python3
import argparse
import time

from common_http import DEFAULT_BASE_URL, http_json, load_progress_fields, print_artifacts, resolve_token, write_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark server inference status API latency and payload cadence.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--role", choices=["admin", "user"], default="admin")
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    token = resolve_token(args.base_url, args.token, args.username, args.password, timeout=args.timeout)
    endpoint = "/admin/inference/status" if args.role == "admin" else "/inference/status"
    rows = []
    for index in range(args.repeat):
        result = http_json("GET", args.base_url, endpoint, token=token, timeout=args.timeout)
        row = {
            "case": "status_poll",
            "index": index,
            "endpoint": endpoint,
            "status": result["status"],
            "ok": result["ok"],
            "latency_sec": result["latency_sec"],
            "error": result["error"],
        }
        row.update(load_progress_fields(result.get("payload")))
        rows.append(row)
        print(
            f"status_poll index={index} status={row['status']} latency={row['latency_sec']:.4f}s "
            f"state={row.get('load_state')}"
        )
        if index + 1 < args.repeat and args.interval > 0:
            time.sleep(args.interval)

    paths = write_artifacts(
        "server_status_api",
        rows,
        {
            "base_url": args.base_url,
            "endpoint": endpoint,
            "repeat": args.repeat,
            "interval_sec": args.interval,
        },
    )
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

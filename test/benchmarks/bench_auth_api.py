#!/usr/bin/env python3
import argparse
import time

from common_http import DEFAULT_BASE_URL, http_json, print_artifacts, write_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark server auth/login API and basic backend reachability.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    rows = []
    for index in range(args.repeat):
        result = http_json(
            "POST",
            args.base_url,
            "/auth/login",
            body={"username": args.username, "password": args.password},
            timeout=args.timeout,
        )
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        rows.append(
            {
                "case": "auth_login",
                "index": index,
                "status": result["status"],
                "ok": result["ok"] and bool(payload.get("access_token")),
                "latency_sec": result["latency_sec"],
                "token_type": payload.get("token_type"),
                "user_role": (payload.get("user") or {}).get("role") if isinstance(payload.get("user"), dict) else None,
                "error": result["error"],
                "payload_preview": str(result.get("payload"))[:300],
            }
        )
        row = rows[-1]
        print(f"auth_login index={index} status={row['status']} ok={row['ok']} latency={row['latency_sec']:.4f}s")
        if index + 1 < args.repeat and args.interval > 0:
            time.sleep(args.interval)

    paths = write_artifacts(
        "server_auth_api",
        rows,
        {
            "base_url": args.base_url,
            "repeat": args.repeat,
            "interval_sec": args.interval,
            "username": args.username,
        },
    )
    print_artifacts(paths)
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import argparse
import time

from common_http import DEFAULT_BASE_URL, http_json, load_progress_fields, print_artifacts, resolve_token, write_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark server model list and model switch API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--model", action="append", default=[], help="Model id to switch to. Can be repeated.")
    parser.add_argument("--limit", type=int, default=2, help="Max ready models to switch when --model is omitted.")
    parser.add_argument("--poll-after-switch", type=float, default=3.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    token = resolve_token(args.base_url, args.token, args.username, args.password, timeout=30)
    rows = []
    list_result = http_json("GET", args.base_url, "/inference/models", token=token, timeout=30)
    payload = list_result.get("payload") if isinstance(list_result.get("payload"), dict) else {}
    models = payload.get("models") if isinstance(payload.get("models"), list) else []
    rows.append(
        {
            "case": "list_models",
            "index": 0,
            "status": list_result["status"],
            "ok": list_result["ok"],
            "latency_sec": list_result["latency_sec"],
            "model_count": len(models),
            "current_model_id": payload.get("current_model_id"),
            "error": list_result["error"],
        }
    )
    if not list_result["ok"]:
        paths = write_artifacts("server_model_switch_api", rows, {"base_url": args.base_url})
        print_artifacts(paths)
        return 1

    selected_ids = list(args.model)
    if not selected_ids:
        selected_ids = [str(item.get("id")) for item in models if item.get("ready")][: max(0, args.limit)]

    for index, model_id in enumerate(selected_ids):
        switch_result = http_json(
            "POST",
            args.base_url,
            "/inference/model/select",
            token=token,
            body={"model_id": model_id},
            timeout=args.timeout,
        )
        row = {
            "case": "model_select",
            "index": index,
            "model_id": model_id,
            "status": switch_result["status"],
            "ok": switch_result["ok"],
            "latency_sec": switch_result["latency_sec"],
            "error": switch_result["error"],
        }
        row.update(load_progress_fields(switch_result.get("payload")))
        rows.append(row)
        print(
            f"model_select model={model_id} status={row['status']} latency={row['latency_sec']:.3f}s "
            f"state={row.get('load_state')}"
        )

        deadline = time.perf_counter() + max(0.0, args.poll_after_switch)
        poll_index = 0
        while time.perf_counter() < deadline:
            time.sleep(max(0.0, args.poll_interval))
            status_result = http_json("GET", args.base_url, "/inference/status", token=token, timeout=30)
            poll_row = {
                "case": "post_switch_status_poll",
                "index": poll_index,
                "model_id": model_id,
                "status": status_result["status"],
                "ok": status_result["ok"],
                "latency_sec": status_result["latency_sec"],
                "error": status_result["error"],
            }
            poll_row.update(load_progress_fields(status_result.get("payload")))
            rows.append(poll_row)
            poll_index += 1

    paths = write_artifacts(
        "server_model_switch_api",
        rows,
        {
            "base_url": args.base_url,
            "requested_models": selected_ids,
            "poll_after_switch_sec": args.poll_after_switch,
            "poll_interval_sec": args.poll_interval,
        },
    )
    print_artifacts(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

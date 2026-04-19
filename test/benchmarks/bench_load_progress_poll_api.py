#!/usr/bin/env python3
import argparse
import threading
import time

from common_http import DEFAULT_BASE_URL, http_json, load_progress_fields, print_artifacts, resolve_token, write_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll server load progress while a model switch is running.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--model", default=None, help="Model id to switch to. Defaults to the first ready unselected model.")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--max-polls", type=int, default=120)
    args = parser.parse_args()

    token = resolve_token(args.base_url, args.token, args.username, args.password, timeout=30)
    rows = []

    models_result = http_json("GET", args.base_url, "/inference/models", token=token, timeout=30)
    payload = models_result.get("payload") if isinstance(models_result.get("payload"), dict) else {}
    models = payload.get("models") if isinstance(payload.get("models"), list) else []
    current_id = payload.get("current_model_id")
    model_id = args.model
    if not model_id:
        for item in models:
            if item.get("ready") and item.get("id") != current_id:
                model_id = str(item.get("id"))
                break
        if not model_id:
            for item in models:
                if item.get("ready"):
                    model_id = str(item.get("id"))
                    break

    rows.append(
        {
            "case": "list_models",
            "index": 0,
            "status": models_result["status"],
            "ok": models_result["ok"] and bool(model_id),
            "latency_sec": models_result["latency_sec"],
            "model_count": len(models),
            "current_model_id": current_id,
            "model_id": model_id,
            "error": models_result["error"],
        }
    )
    if not model_id:
        paths = write_artifacts("server_load_progress_poll_api", rows, {"base_url": args.base_url})
        print_artifacts(paths)
        return 1

    switch_holder = {}

    def switch_model() -> None:
        switch_holder["result"] = http_json(
            "POST",
            args.base_url,
            "/inference/model/select",
            token=token,
            body={"model_id": model_id},
            timeout=args.timeout,
        )

    thread = threading.Thread(target=switch_model, daemon=True)
    started = time.perf_counter()
    thread.start()

    for index in range(args.max_polls):
        result = http_json("GET", args.base_url, "/inference/status", token=token, timeout=30)
        row = {
            "case": "load_progress_poll",
            "index": index,
            "elapsed_since_switch_start_sec": round(time.perf_counter() - started, 6),
            "model_id": model_id,
            "status": result["status"],
            "ok": result["ok"],
            "latency_sec": result["latency_sec"],
            "error": result["error"],
        }
        row.update(load_progress_fields(result.get("payload")))
        rows.append(row)
        print(
            f"load_progress_poll index={index} status={row['status']} state={row.get('load_state')} "
            f"percent={row.get('load_percent')}"
        )
        if not thread.is_alive():
            break
        time.sleep(max(0.0, args.poll_interval))

    thread.join(timeout=1)
    switch_result = switch_holder.get("result")
    if switch_result:
        row = {
            "case": "model_select_result",
            "index": 0,
            "model_id": model_id,
            "status": switch_result["status"],
            "ok": switch_result["ok"],
            "latency_sec": switch_result["latency_sec"],
            "error": switch_result["error"],
        }
        row.update(load_progress_fields(switch_result.get("payload")))
        rows.append(row)

    paths = write_artifacts(
        "server_load_progress_poll_api",
        rows,
        {
            "base_url": args.base_url,
            "model_id": model_id,
            "poll_interval_sec": args.poll_interval,
            "max_polls": args.max_polls,
        },
    )
    print_artifacts(paths)
    return 0 if switch_result and switch_result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

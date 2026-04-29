#!/usr/bin/env python3
"""文件说明：HTTP 基准测试脚本，压测 common_http 对应的服务端接口。"""

import csv
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TEST_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = TEST_DIR / "benchmark_reports"
DEFAULT_BASE_URL = os.getenv("SERVER_BENCH_BASE_URL", "http://127.0.0.1:8000/api")


def normalize_base_url(value: str) -> str:
    base = str(value or DEFAULT_BASE_URL).strip().rstrip("/")
    if base.endswith("/api"):
        return base
    return base + "/api"


def parse_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def http_json(
    method: str,
    base_url: str,
    path: str,
    token: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    url = path if path.startswith("http") else normalize_base_url(base_url) + "/" + path.lstrip("/")
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - started
            payload = parse_json(raw_text)
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "latency_sec": round(elapsed, 6),
                "payload": payload,
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        raw_text = exc.read().decode("utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        return {
            "ok": False,
            "status": exc.code,
            "latency_sec": round(elapsed, 6),
            "payload": parse_json(raw_text),
            "error": str(exc),
        }
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return {
            "ok": False,
            "status": None,
            "latency_sec": round(elapsed, 6),
            "payload": None,
            "error": str(exc),
        }


def resolve_token(
    base_url: str,
    token: Optional[str],
    username: Optional[str],
    password: Optional[str],
    timeout: float = 30.0,
) -> str:
    explicit = token or os.getenv("SERVER_BENCH_TOKEN")
    if explicit:
        return explicit

    user = username or os.getenv("SERVER_BENCH_USERNAME")
    pwd = password or os.getenv("SERVER_BENCH_PASSWORD")
    if not user or not pwd:
        raise RuntimeError("需要提供 --token，或提供 --username/--password，或设置 SERVER_BENCH_TOKEN。")

    result = http_json("POST", base_url, "/auth/login", body={"username": user, "password": pwd}, timeout=timeout)
    if not result["ok"]:
        raise RuntimeError(f"登录失败: status={result['status']} payload={result['payload']} error={result['error']}")
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError(f"登录响应缺少 access_token: {payload}")
    return str(access_token)


def percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 6)
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    value = ordered[lower] * (1 - weight) + ordered[upper] * weight
    return round(value, 6)


def summarize_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    materialized = list(rows)
    latencies = [float(row["latency_sec"]) for row in materialized if isinstance(row.get("latency_sec"), (int, float))]
    statuses: Dict[str, int] = {}
    for row in materialized:
        status = str(row.get("status"))
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "row_count": len(materialized),
        "ok_count": sum(1 for row in materialized if row.get("ok") is True),
        "status_counts": statuses,
        "latency_min_sec": round(min(latencies), 6) if latencies else None,
        "latency_avg_sec": round(sum(latencies) / len(latencies), 6) if latencies else None,
        "latency_p50_sec": percentile(latencies, 0.50),
        "latency_p95_sec": percentile(latencies, 0.95),
        "latency_max_sec": round(max(latencies), 6) if latencies else None,
    }


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def write_artifacts(test_name: str, rows: List[Dict[str, Any]], metadata: Dict[str, Any]) -> Dict[str, str]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = REPORT_DIR / f"{stamp}_{test_name}"
    payload = {
        "test_name": test_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": metadata,
        "summary": summarize_rows(rows),
        "rows": rows,
    }
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    md_path = base.with_suffix(".md")

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = sorted({key for row in rows for key in row.keys()})
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in keys})

    lines = [
        f"# {test_name}",
        "",
        f"- Created at: {payload['created_at']}",
        f"- Row count: {len(rows)}",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(payload["summary"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Metadata",
        "",
        "```json",
        json.dumps(metadata, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Results",
        "",
    ]
    if rows:
        display_keys = [
            "case",
            "index",
            "model_id",
            "message_id",
            "status",
            "ok",
            "latency_sec",
            "ready",
            "running",
            "load_state",
            "load_percent",
            "response_chars",
            "error",
        ]
        display_keys = [key for key in display_keys if any(key in row for row in rows)]
        lines.append("| " + " | ".join(display_keys) + " |")
        lines.append("| " + " | ".join(["---"] * len(display_keys)) + " |")
        for row in rows:
            values = [str(row.get(key, ""))[:180].replace("\n", " ") for key in display_keys]
            lines.append("| " + " | ".join(values) + " |")
    else:
        lines.append("No rows.")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}


def print_artifacts(paths: Dict[str, str]) -> None:
    print("Wrote reports:")
    for kind, path in paths.items():
        print(f"  {kind}: {path}")


def load_progress_fields(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    progress = payload.get("model_loading_progress")
    if not isinstance(progress, dict):
        progress = {}
    loaded = progress.get("loaded_bytes")
    total = progress.get("total_bytes")
    percent = None
    if isinstance(loaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
        percent = round(float(loaded) * 100.0 / float(total), 3)
    return {
        "ready": payload.get("ready"),
        "running": payload.get("running"),
        "active_request_id": payload.get("active_request_id"),
        "current_model_id": payload.get("current_model_id"),
        "current_model_name": payload.get("current_model_name"),
        "current_model_seq_len": payload.get("current_model_seq_len"),
        "load_state": progress.get("state"),
        "load_stage": progress.get("stage"),
        "load_loaded_bytes": loaded,
        "load_total_bytes": total,
        "load_percent": percent,
    }

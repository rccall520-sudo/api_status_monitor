#!/usr/bin/env python3
"""
API Status Monitor - 探测脚本
支持统一配置多个站点和模型的可用性监测
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

DEFAULT_MODEL = "gpt-3.5-turbo"
HISTORY_DAYS = 7
DATA_VERSION = 2
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "docs" / "data"
STATUS_PATH = DATA_DIR / "status.json"
HISTORY_PATH = DATA_DIR / "history.json"


def load_dotenv(path: Path) -> None:
    """加载 .env 文件。"""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "target"


def extract_api_base(base_url: str) -> str:
    if not base_url:
        return "-"
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    return parsed.netloc or parsed.path.split("/")[0] or "-"


def load_json_or_default(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_url(base: str, path: str) -> str:
    base_clean = base.rstrip("/")
    path_clean = path.strip("/")
    if base_clean.endswith(path_clean):
        return base_clean
    return (
        f"{base_clean}/{path_clean}"
        if re.search(r"/v\d+(/|$)", base_clean)
        else f"{base_clean}/v1/{path_clean}"
    )


def normalize_target_config(raw: Dict[str, Any], index: int) -> Dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"第 {index + 1} 个监控目标不是对象")

    base_url = str(
        raw.get("base_url")
        or raw.get("api_base_url")
        or raw.get("api_base")
        or raw.get("url")
        or ""
    ).strip()
    api_key = str(raw.get("api_key") or raw.get("key") or get_env("API_KEY")).strip()
    model = str(raw.get("model") or get_env("API_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL

    if not base_url:
        raise ValueError(f"第 {index + 1} 个监控目标缺少 base_url")
    if not api_key:
        raise ValueError(f"第 {index + 1} 个监控目标缺少 api_key")

    api_base = extract_api_base(base_url)
    name = str(raw.get("name") or raw.get("label") or f"{api_base} · {model}").strip()
    target_id = str(raw.get("target_id") or raw.get("id") or slugify(name or f"{api_base}-{model}")).strip()

    return {
        "target_id": target_id,
        "name": name,
        "base_url": base_url,
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
    }


def dedupe_target_ids(targets: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: Dict[str, int] = {}
    for target in targets:
        base_id = target["target_id"] or "target"
        seen[base_id] = seen.get(base_id, 0) + 1
        if seen[base_id] > 1:
            target["target_id"] = f"{base_id}-{seen[base_id]}"
    return targets


def load_targets() -> List[Dict[str, str]]:
    raw_targets = get_env("MONITOR_TARGETS")
    if raw_targets:
        try:
            parsed = json.loads(raw_targets)
        except json.JSONDecodeError as exc:
            raise ValueError(f"MONITOR_TARGETS 不是合法 JSON: {exc}") from exc

        if not isinstance(parsed, list) or not parsed:
            raise ValueError("MONITOR_TARGETS 必须是非空 JSON 数组")

        targets = [normalize_target_config(item, index) for index, item in enumerate(parsed)]
        return dedupe_target_ids(targets)

    base_url = get_env("API_BASE_URL")
    api_key = get_env("API_KEY")
    model = get_env("API_MODEL", DEFAULT_MODEL)
    if not base_url or not api_key:
        return []

    return [
        normalize_target_config(
            {
                "name": f"{extract_api_base(base_url)} · {model}",
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
            },
            0,
        )
    ]


def build_target_lookup(targets: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {target["target_id"]: target for target in targets}


def resolve_target_for_entry(entry: Dict[str, Any], targets: List[Dict[str, str]]) -> Dict[str, str]:
    target_id = str(entry.get("target_id") or "").strip()
    if target_id:
        for target in targets:
            if target["target_id"] == target_id:
                return target

    api_base = str(entry.get("api_base") or "").strip()
    model = str(entry.get("model") or "").strip()
    for target in targets:
        if api_base and model and target["api_base"] == api_base and target["model"] == model:
            return target

    fallback_name = str(entry.get("target_name") or entry.get("name") or f"{api_base or 'unknown'} · {model or DEFAULT_MODEL}")
    return {
        "target_id": target_id or slugify(fallback_name),
        "name": fallback_name,
        "base_url": "",
        "api_base": api_base or "-",
        "api_key": "",
        "model": model or DEFAULT_MODEL,
    }


def normalize_result(entry: Dict[str, Any], target: Dict[str, str]) -> Dict[str, Any]:
    timestamp = entry.get("timestamp") or entry.get("last_check") or iso_z(utc_now())
    return {
        "target_id": target["target_id"],
        "target_name": target["name"],
        "timestamp": timestamp,
        "last_check": timestamp,
        "api_base": entry.get("api_base") or target["api_base"],
        "model": entry.get("model") or target["model"],
        "http_status": entry.get("http_status"),
        "latency_ms": entry.get("latency_ms"),
        "success": bool(entry.get("success")),
        "token_output": bool(entry.get("token_output")),
        "error_message": entry.get("error_message") or "",
    }


def extract_history_entries(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return [item for item in payload["entries"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def normalize_history(history_payload: Any, targets: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for entry in extract_history_entries(history_payload):
        target = resolve_target_for_entry(entry, targets)
        normalized.append(normalize_result(entry, target))

    normalized.sort(
        key=lambda entry: parse_iso(entry.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)
    )
    return normalized


def cleanup_old_history(history: List[Dict[str, Any]], days: int = HISTORY_DAYS) -> List[Dict[str, Any]]:
    cutoff = utc_now().timestamp() - days * 24 * 3600
    result = []
    for entry in history:
        dt = parse_iso(entry.get("timestamp") or entry.get("last_check"))
        if dt and dt.timestamp() > cutoff:
            result.append(entry)
    return result


def calculate_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(entries)
    success_count = sum(1 for entry in entries if entry.get("success"))
    latencies = [
        entry["latency_ms"]
        for entry in entries
        if isinstance(entry.get("latency_ms"), (int, float))
    ]
    return {
        "total_checks": total,
        "success_checks": success_count,
        "failure_checks": total - success_count,
        "uptime": round(success_count / total * 100, 1) if total else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
    }


def build_status_payload(statuses: List[Dict[str, Any]]) -> Dict[str, Any]:
    stats = calculate_stats(statuses)
    return {
        "version": DATA_VERSION,
        "updated_at": iso_z(utc_now()),
        "summary": {
            "target_count": len(statuses),
            "online_count": stats["success_checks"],
            "offline_count": stats["failure_checks"],
            "overall_success": bool(statuses) and stats["failure_checks"] == 0,
        },
        "targets": statuses,
    }


def build_history_payload(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "version": DATA_VERSION,
        "updated_at": iso_z(utc_now()),
        "entries": history,
    }


def probe_api(base_url: str, api_key: str, model: str) -> Dict[str, Any]:
    url = make_url(base_url, "chat/completions")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    result = {
        "timestamp": iso_z(utc_now()),
        "success": False,
        "http_status": None,
        "latency_ms": None,
        "token_output": False,
        "error_message": None,
        "model": model,
    }

    try:
        req_data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

        start_time = time.time()
        with urllib.request.urlopen(request, timeout=30) as response:
            latency_ms = int((time.time() - start_time) * 1000)
            result["http_status"] = response.status
            result["latency_ms"] = latency_ms

            if response.status != 200:
                result["error_message"] = f"HTTP {response.status}"
                return result

            raw = response.read().decode("utf-8")
            try:
                body = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                result["error_message"] = "Invalid JSON response"
                return result

            if not isinstance(body, dict):
                result["error_message"] = f"Unexpected response type: {type(body).__name__}"
                return result

            choices = body.get("choices")
            if not choices or not isinstance(choices, list):
                err = body.get("error")
                result["error_message"] = err.get("message", str(err)) if isinstance(err, dict) else "No choices in response"
                return result

            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                result["error_message"] = "Unexpected choice format"
                return result

            message = first_choice.get("message")
            content = message.get("content", "") if isinstance(message, dict) else ""
            result["success"] = True
            result["token_output"] = bool(content)

    except urllib.error.HTTPError as exc:
        result["http_status"] = exc.code
        result["error_message"] = f"HTTP {exc.code}: {exc.reason}"
        try:
            error_body = json.loads(exc.read().decode("utf-8"))
            if isinstance(error_body, dict) and "error" in error_body:
                err = error_body["error"]
                result["error_message"] = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        except Exception:
            pass
    except urllib.error.URLError as exc:
        result["error_message"] = f"Connection error: {exc.reason}"
    except Exception as exc:
        result["error_message"] = f"Error: {exc}"

    return result


def run_checks(targets: List[Dict[str, str]]) -> Dict[str, Any]:
    if not targets:
        raise ValueError("未找到可用监控目标，请配置 MONITOR_TARGETS 或旧版 API_BASE_URL / API_KEY")

    statuses: List[Dict[str, Any]] = []
    for target in targets:
        raw_result = probe_api(target["base_url"], target["api_key"], target["model"])
        statuses.append(normalize_result(raw_result, target))

    statuses.sort(key=lambda item: item["target_name"])
    history = normalize_history(load_json_or_default(HISTORY_PATH, {"entries": []}), targets)
    history.extend(statuses)
    history = cleanup_old_history(history, HISTORY_DAYS)

    status_payload = build_status_payload(statuses)
    history_payload = build_history_payload(history)

    save_json(STATUS_PATH, status_payload)
    save_json(HISTORY_PATH, history_payload)

    return {
        "statuses": statuses,
        "history": history,
        "status_payload": status_payload,
        "history_payload": history_payload,
        "history_stats": calculate_stats(history),
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        targets = load_targets()
    except ValueError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    if not targets:
        print("错误: 请配置 MONITOR_TARGETS，或保留旧版 API_BASE_URL / API_KEY")
        sys.exit(1)

    print(f"本次监控目标: {len(targets)} 个")
    for target in targets:
        print(f"  - {target['name']} | {target['api_base']} | {target['model']}")

    result = run_checks(targets)
    print("\n检测结果:")
    for status in result["statuses"]:
        print(
            f"  {'✓' if status['success'] else '✗'} "
            f"{status['target_name']} | "
            f"{status['latency_ms'] or 'N/A'}ms | "
            f"HTTP {status['http_status'] or 'N/A'}"
        )
        if status["error_message"]:
            print(f"    错误: {status['error_message']}")

    history_stats = result["history_stats"]
    print(f"\n状态已保存到: {STATUS_PATH}")
    print(f"历史已保存到: {HISTORY_PATH}")
    print(f"历史记录: {history_stats['total_checks']} 次探测")
    print(f"可用率: {history_stats['uptime']:.1f}%")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
API Status Monitor - 探测脚本
支持多种API格式的可用性监测
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
from typing import Any, Dict, List, Optional, Tuple

# 配置常量
HISTORY_DAYS = 7
HOURS_IN_HISTORY = 24 * HISTORY_DAYS
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "docs" / "data"
STATUS_PATH = DATA_DIR / "status.json"
HISTORY_PATH = DATA_DIR / "history.json"


def load_dotenv(path: Path) -> None:
    """加载.env文件"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    """ISO格式时间戳"""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_url(base: str, path: str) -> str:
    """构建完整URL"""
    b, p = base.rstrip("/"), path.strip("/")
    if b.endswith(p):
        return b
    return f"{b}/{p}" if re.search(r"/v\d+(/|$)", b) else f"{b}/v1/{p}"


def probe_api(base_url: str, api_key: str, model: str) -> Dict[str, Any]:
    """
    发送探测请求，返回结果
    """
    url = make_url(base_url, "chat/completions")
    
    # 最小化请求体
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1,
        "stream": False
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
        "model": model
    }
    
    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

        start_time = time.time()
        with urllib.request.urlopen(req, timeout=30) as response:
            latency_ms = int((time.time() - start_time) * 1000)
            result["http_status"] = response.status
            result["latency_ms"] = latency_ms

            if response.status == 200:
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
                if not choices or not isinstance(choices, list) or len(choices) == 0:
                    # 可能是 OpenAI 兼容格式的错误响应（200 但有 error 字段）
                    err = body.get("error")
                    if isinstance(err, dict):
                        result["error_message"] = err.get("message", str(err))
                    else:
                        result["error_message"] = "No choices in response"
                    return result

                choice = choices[0]
                if not isinstance(choice, dict):
                    result["error_message"] = f"Unexpected choice format"
                    return result

                message = choice.get("message")
                content = message.get("content", "") if isinstance(message, dict) else ""

                if content:
                    result["success"] = True
                    result["token_output"] = True
                    result["error_message"] = None
                else:
                    result["error_message"] = "Empty response content"
            else:
                result["error_message"] = f"HTTP {response.status}"

    except urllib.error.HTTPError as e:
        result["http_status"] = e.code
        result["error_message"] = f"HTTP {e.code}: {e.reason}"
        try:
            error_body = json.loads(e.read().decode("utf-8"))
            if isinstance(error_body, dict) and "error" in error_body:
                err = error_body["error"]
                result["error_message"] = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        except Exception:
            pass
    except urllib.error.URLError as e:
        result["error_message"] = f"Connection error: {e.reason}"
    except Exception as e:
        result["error_message"] = f"Error: {str(e)}"
    
    return result


def load_json_or_default(path: Path, default: Any) -> Any:
    """加载JSON文件，不存在则返回默认值"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return default


def save_json(path: Path, data: Any) -> None:
    """保存JSON文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def aggregate_hourly(history: List[Dict]) -> Dict[str, Dict]:
    """按小时聚合历史数据"""
    hourly = {}
    for entry in history:
        dt = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        hour_key = dt.strftime("%Y-%m-%d %H:00")
        
        if hour_key not in hourly:
            hourly[hour_key] = {"success": 0, "total": 0}
        
        hourly[hour_key]["total"] += 1
        if entry.get("success"):
            hourly[hour_key]["success"] += 1
    
    return hourly


def cleanup_old_history(history: List[Dict], days: int = 7) -> List[Dict]:
    """清理超过N天的历史记录"""
    cutoff = utc_now().timestamp() - days * 24 * 3600
    return [h for h in history if datetime.fromisoformat(
        h["timestamp"].replace("Z", "+00:00")
    ).timestamp() > cutoff]


def main():
    # 加载环境变量
    load_dotenv(PROJECT_ROOT / ".env")
    
    base_url = os.environ.get("API_BASE_URL", "")
    api_key = os.environ.get("API_KEY", "")
    model = os.environ.get("API_MODEL", "gpt-3.5-turbo")
    
    if not base_url or not api_key:
        print("错误: 请配置 API_BASE_URL 和 API_KEY")
        print("您可以: 1) 创建 .env 文件  2) 设置环境变量")
        sys.exit(1)
    
    print(f"正在探测: {base_url}")
    print(f"模型: {model}")
    
    # 执行探测
    result = probe_api(base_url, api_key, model)
    
    print(f"\n结果:")
    print(f"  HTTP状态: {result['http_status'] or 'N/A'}")
    print(f"  延迟: {result['latency_ms']}ms" if result['latency_ms'] else "  延迟: N/A")
    print(f"  成功: {'✓' if result['success'] else '✗'}")
    print(f"  输出token: {'✓' if result['token_output'] else '✗'}")
    if result['error_message']:
        print(f"  错误: {result['error_message']}")
    
    # 更新状态文件
    status = {
        "last_check": result["timestamp"],
        "api_base": base_url.split("//")[-1].split("/")[0],  # 只显示域名
        "model": model,
        "http_status": result["http_status"],
        "latency_ms": result["latency_ms"],
        "success": result["success"],
        "token_output": result["token_output"],
        "error_message": result["error_message"]
    }
    save_json(STATUS_PATH, status)
    print(f"\n状态已保存到: {STATUS_PATH}")
    
    # 更新历史文件
    history = load_json_or_default(HISTORY_PATH, [])
    history.append(result)
    history = cleanup_old_history(history, HISTORY_DAYS)
    save_json(HISTORY_PATH, history)
    
    # 计算可用率
    hourly = aggregate_hourly(history)
    total_checks = len(history)
    success_checks = sum(1 for h in history if h.get("success"))
    uptime = success_checks / total_checks * 100 if total_checks > 0 else 0
    
    print(f"历史记录: {total_checks} 次探测")
    print(f"可用率: {uptime:.1f}%")
    print(f"历史已保存到: {HISTORY_PATH}")


if __name__ == "__main__":
    main()
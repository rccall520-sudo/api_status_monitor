#!/usr/bin/env python3
"""
API监控守护进程 - 每10分钟自动检测，复用 scripts/check_api.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from check_api import (
    load_dotenv, probe_api, save_json, load_json_or_default,
    cleanup_old_history, STATUS_PATH, HISTORY_PATH, HISTORY_DAYS,
)


def check_and_save():
    base_url = os.environ.get("API_BASE_URL", "")
    api_key = os.environ.get("API_KEY", "")
    model = os.environ.get("API_MODEL", "gpt-3.5-turbo")

    result = probe_api(base_url, api_key, model)

    status = result.copy()
    status["last_check"] = result["timestamp"]
    save_json(STATUS_PATH, status)

    history = load_json_or_default(HISTORY_PATH, [])
    history.append(result)
    history = cleanup_old_history(history, HISTORY_DAYS)
    save_json(HISTORY_PATH, history)

    total = len(history)
    success = sum(1 for h in history if h.get("success"))
    uptime = success / total * 100 if total > 0 else 0
    print(f"{'✓' if result['success'] else '✗'} "
          f"{result['latency_ms'] or '?'}ms | "
          f"历史{total}次 可用率{uptime:.1f}%")


def main():
    load_dotenv(Path(__file__).parent / ".env")

    base_url = os.environ.get("API_BASE_URL", "")
    api_key = os.environ.get("API_KEY", "")
    model = os.environ.get("API_MODEL", "gpt-3.5-turbo")

    if not base_url or not api_key:
        print("错误: 请在 .env 中配置 API_BASE_URL 和 API_KEY")
        sys.exit(1)

    print(f"API监控启动 | {base_url} | {model} | 间隔10分钟 | Ctrl+C 停止")

    check_and_save()

    while True:
        try:
            time.sleep(600)
            check_and_save()
        except KeyboardInterrupt:
            print("\n服务已停止")
            break
        except Exception as e:
            print(f"出错: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()

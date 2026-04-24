#!/usr/bin/env python3
"""
API监控守护进程 - 每10分钟自动检测，复用 scripts/check_api.py
"""
import os
import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from check_api import (
    DEFAULT_MODEL,
    HISTORY_DAYS,
    HISTORY_PATH,
    STATUS_PATH,
    cleanup_old_history,
    get_env,
    load_dotenv,
    load_json_or_default,
    normalize_history,
    normalize_result,
    probe_api,
    save_json,
)

DEFAULT_INTERVAL_SECONDS = 600


def run_git(args):
    return subprocess.run(args, cwd=Path(__file__).parent, capture_output=True, text=True)


def git_push():
    """提交并推送检测数据到 GitHub"""
    try:
        run_git(["git", "add", "docs/data/"])
        staged = run_git(["git", "diff", "--staged", "--quiet"])
        if staged.returncode == 0:
            return

        commit = run_git(["git", "commit", "-m", "Update status"])
        if commit.returncode != 0:
            print(f"  → 提交失败: {commit.stderr.strip() or commit.stdout.strip()}")
            return

        pull = run_git(["git", "pull", "--rebase", "--autostash", "origin", "main"])
        if pull.returncode != 0:
            print(f"  → 同步远端失败: {pull.stderr.strip() or pull.stdout.strip()}")
            return

        push = run_git(["git", "push", "origin", "main"])
        if push.returncode != 0:
            print(f"  → 推送失败: {push.stderr.strip() or push.stdout.strip()}")
            return

        print("  → 已推送到 GitHub")
    except Exception as e:
        print(f"  → 推送失败: {e}")


def check_and_save():
    base_url = get_env("API_BASE_URL")
    api_key = get_env("API_KEY")
    model = get_env("API_MODEL", DEFAULT_MODEL)

    result = probe_api(base_url, api_key, model)
    status = normalize_result(result, base_url, model)

    save_json(STATUS_PATH, status)

    history = normalize_history(load_json_or_default(HISTORY_PATH, []), base_url, model)
    history.append(status)
    history = cleanup_old_history(history, HISTORY_DAYS)
    save_json(HISTORY_PATH, history)

    total = len(history)
    success = sum(1 for h in history if h.get("success"))
    uptime = success / total * 100 if total > 0 else 0
    print(f"{'✓' if status['success'] else '✗'} "
          f"{status['latency_ms'] or '?'}ms | "
          f"历史{total}次 可用率{uptime:.1f}%")

    git_push()


def main():
    load_dotenv(Path(__file__).parent / ".env")

    base_url = get_env("API_BASE_URL")
    api_key = get_env("API_KEY")
    model = get_env("API_MODEL", DEFAULT_MODEL)
    interval_seconds = int(get_env("CHECK_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)))

    if not base_url or not api_key:
        print("错误: 请在 .env 中配置 API_BASE_URL 和 API_KEY")
        sys.exit(1)

    print(f"API监控启动 | {base_url} | {model} | 间隔{interval_seconds // 60}分钟 | Ctrl+C 停止")

    while True:
        started_at = time.monotonic()
        try:
            check_and_save()
        except KeyboardInterrupt:
            print("\n服务已停止")
            break
        except Exception as e:
            print(f"出错: {e}")
        sleep_seconds = max(0, interval_seconds - (time.monotonic() - started_at))
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()

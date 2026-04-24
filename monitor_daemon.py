#!/usr/bin/env python3
"""
API 监控守护进程 - 每 10 分钟自动检测，可统一配置多个站点和模型
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from check_api import DEFAULT_MODEL, get_env, load_dotenv, load_targets, run_checks

DEFAULT_INTERVAL_SECONDS = 600


def run_git(args):
    return subprocess.run(args, cwd=Path(__file__).parent, capture_output=True, text=True)


def git_push():
    """提交并推送检测数据到 GitHub。"""
    try:
        run_git(["git", "add", "docs/data/"])
        staged = run_git(["git", "diff", "--staged", "--quiet"])
        if staged.returncode == 0:
            return

        commit = run_git(["git", "commit", "-m", "Update status"])
        if commit.returncode != 0:
            print(f"  -> 提交失败: {commit.stderr.strip() or commit.stdout.strip()}")
            return

        pull = run_git(["git", "pull", "--rebase", "--autostash", "origin", "main"])
        if pull.returncode != 0:
            print(f"  -> 同步远端失败: {pull.stderr.strip() or pull.stdout.strip()}")
            return

        push = run_git(["git", "push", "origin", "main"])
        if push.returncode != 0:
            print(f"  -> 推送失败: {push.stderr.strip() or push.stdout.strip()}")
            return

        print("  -> 已推送到 GitHub")
    except Exception as exc:
        print(f"  -> 推送失败: {exc}")


def check_and_save(targets):
    result = run_checks(targets)
    for status in result["statuses"]:
        print(
            f"{'✓' if status['success'] else '✗'} "
            f"{status['target_name']} | "
            f"{status['latency_ms'] or '?'}ms | "
            f"HTTP {status['http_status'] or 'N/A'}"
        )
    print(
        f"历史{result['history_stats']['total_checks']}次 "
        f"可用率{result['history_stats']['uptime']:.1f}%"
    )
    git_push()


def main():
    load_dotenv(Path(__file__).parent / ".env")

    try:
        targets = load_targets()
    except ValueError as exc:
        print(f"错误: {exc}")
        sys.exit(1)

    if not targets:
        print("错误: 请配置 MONITOR_TARGETS，或保留旧版 API_BASE_URL / API_KEY")
        sys.exit(1)

    interval_seconds = int(get_env("CHECK_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)))
    print(
        f"API监控启动 | {len(targets)}个目标 | "
        f"默认模型 {get_env('API_MODEL', DEFAULT_MODEL)} | "
        f"间隔{interval_seconds // 60}分钟 | Ctrl+C 停止"
    )

    for target in targets:
        print(f"  - {target['name']} | {target['api_base']} | {target['model']}")

    while True:
        started_at = time.monotonic()
        try:
            check_and_save(targets)
        except KeyboardInterrupt:
            print("\n服务已停止")
            break
        except Exception as exc:
            print(f"出错: {exc}")

        sleep_seconds = max(0, interval_seconds - (time.monotonic() - started_at))
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import sys

from stocker.jobs import StockerApp
from stocker.scheduler import run_scheduler


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Stocker 台股情報 Telegram 機器人")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="本機常駐排程（電腦需開機）")
    sub.add_parser("test", help="發送一則 Telegram 測試訊息")
    sub.add_parser("mops", help="立刻抓一次重大訊息（高重要性才推播）")
    daily = sub.add_parser("daily", help="立刻產生並推播每日摘要")
    daily.add_argument("--print-only", action="store_true", help="只印出摘要、不推播")
    etf = sub.add_parser("etf", help="立刻推主動 ETF 共識排行")
    etf.add_argument("--print-only", action="store_true", help="只印出明細、不推播")
    args = parser.parse_args(argv)

    if args.command == "run":
        run_scheduler()
        return 0

    app = StockerApp()
    try:
        if args.command == "test":
            app.send_test()
            print("已送出測試訊息")
            return 0
        if args.command == "mops":
            n = app.poll_mops(send_high=True)
            print(f"新的高重要性訊息：{n} 則")
            return 0
        if args.command == "daily":
            text = app.daily_report(force=True, send=not args.print_only)
            print(text)
            if not args.print_only:
                print("\n已推播每日摘要")
            return 0
        if args.command == "etf":
            text = app.etf_report(send=not args.print_only)
            print(text)
            if not args.print_only:
                print("\n已推播主動 ETF 共識排行")
            return 0
    finally:
        app.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())

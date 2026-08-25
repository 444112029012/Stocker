from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from stocker.bot import run_bot
from stocker.jobs import StockerApp
from stocker.settings import TZ_NAME


def run_scheduler() -> None:
    app = StockerApp()
    scheduler = BackgroundScheduler(timezone=TZ_NAME)
    scheduler.add_job(
        app.poll_mops,
        CronTrigger(day_of_week="mon-fri", hour="8-17", minute="*/20"),
        id="mops",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        app.daily_report,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=30),
        id="daily",
        max_instances=1,
        coalesce=True,
        kwargs={"force": False},
    )
    scheduler.start()

    print("Stocker 已啟動（本機排程 + Telegram 主選單，電腦需保持開機）")
    print("  平日 08:00-17:40 每 20 分鐘：罕見重訊（停工／減資／私募／併購／董總）")
    print("  平日 21:30：短摘要（重訊 8 則、投信 Top 5、ETF 共識）")
    print("  Telegram 按鈕：立即推播／ETF加減碼／立刻抓重訊／測試連線／使用說明")
    try:
        app.telegram.set_commands()
        app.telegram.send_menu("Stocker 已啟動。點下方按鈕即可立即推播。")
        run_bot(app)
    except KeyboardInterrupt:
        print("已停止")
    finally:
        scheduler.shutdown(wait=False)
        app.close()

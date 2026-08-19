from __future__ import annotations

from stocker.jobs import StockerApp

MENU_TEXT = (
    "Stocker 主選單\n"
    "• 立即推播：重訊 + 投信買賣超 + 主動 ETF\n"
    "• ETF加減碼：每檔實際買賣超股票明細（張數）\n"
    "• 立刻抓重訊：只送尚未推過的高重要性訊息\n"
    "平日排程仍會自動跑（08:00–17:40 重訊、21:30 摘要）。"
)

HELP_TEXT = (
    "使用說明\n\n"
    "立即推播／/daily\n"
    "馬上抓今日重訊、投信買賣超、前五大主動 ETF。\n\n"
    "ETF加減碼／/etf\n"
    "列出每檔主動 ETF 買超／賣超股票、張數與權重變化，以及五檔合計。\n\n"
    "立刻抓重訊／/mops\n"
    "只推還沒送過的高重要性重大訊息。\n\n"
    "測試連線／/start\n"
    "確認機器人還活著，並叫出下方按鈕。\n\n"
    "請保持本機 python -m stocker run 視窗開著。"
)


def handle_message(app: StockerApp, text: str) -> None:
    command = text.strip()
    if command.startswith("/"):
        command = command.split("@", 1)[0].split()[0].lower()

    if command in {"/start", "/menu", "主選單"}:
        app.telegram.send_menu(MENU_TEXT)
        return
    if command in {"/help", "使用說明"}:
        app.telegram.send_menu(HELP_TEXT)
        return
    if command in {"/test", "測試連線"}:
        app.send_test()
        return
    if command in {"/etf", "ETF加減碼", "主動ETF加減碼"}:
        app.telegram.send("正在抓取主動 ETF 買賣超明細，大約 20 秒…")
        app.etf_report(send=True)
        return
    if command in {"/daily", "立即推播"}:
        app.telegram.send("正在抓取每日摘要，大約 20 秒…")
        app.daily_report(force=True, send=True)
        return
    if command in {"/mops", "立刻抓重訊"}:
        app.telegram.send("正在檢查重大訊息…")
        n = app.poll_mops(send_high=True)
        if n == 0:
            app.telegram.send("目前沒有尚未推播的高重要性重訊。")
        return
    app.telegram.send_menu("沒有這個指令。請用下方按鈕，或送 /start。")


def drain_old_updates(app: StockerApp) -> int:
    updates = app.telegram.get_updates(timeout=0)
    if not updates:
        return 0
    return int(updates[-1]["update_id"]) + 1


def run_bot(app: StockerApp) -> None:
    offset = drain_old_updates(app)
    while True:
        updates = app.telegram.get_updates(offset=offset or None, timeout=30)
        for update in updates:
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            text = str(message.get("text") or "").strip()
            if not text:
                continue
            if not app.telegram.allowed_chat(chat.get("id")):
                continue
            try:
                handle_message(app, text)
            except Exception as exc:  # noqa: BLE001
                app.telegram.send(f"執行失敗：{exc}")

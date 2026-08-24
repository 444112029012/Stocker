from __future__ import annotations

from typing import Any

import httpx

from stocker.intelligence.digest import split_message
from stocker.settings import Settings

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "立即推播"}, {"text": "立刻抓重訊"}],
        [{"text": "ETF加減碼"}, {"text": "測試連線"}],
        [{"text": "使用說明"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

BOT_COMMANDS = [
    {"command": "start", "description": "開啟主選單"},
    {"command": "daily", "description": "立即推播每日摘要"},
    {"command": "etf", "description": "主動ETF共識排行"},
    {"command": "mops", "description": "立刻抓重大訊息"},
    {"command": "help", "description": "使用說明"},
]


class TelegramNotifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(timeout=httpx.Timeout(45.0))

    def close(self) -> None:
        self._client.close()

    def enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def allowed_chat(self, chat_id: object) -> bool:
        return str(chat_id) == str(self.settings.telegram_chat_id)

    def send(self, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        if not text.strip():
            return
        if not self.enabled():
            raise RuntimeError("尚未設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": self.settings.telegram_chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if reply_markup is not None and i == 0:
                payload["reply_markup"] = reply_markup
            resp = self._client.post(self._url("sendMessage"), json=payload)
            self._raise_if_failed(resp)

    def send_menu(self, text: str) -> None:
        self.send(text, reply_markup=MAIN_KEYBOARD)

    def set_commands(self) -> None:
        resp = self._client.post(self._url("setMyCommands"), json={"commands": BOT_COMMANDS})
        self._raise_if_failed(resp)

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        resp = self._client.post(
            self._url("getUpdates"),
            json=payload,
            timeout=timeout + 15,
        )
        data = self._raise_if_failed(resp)
        result = data.get("result") or []
        return result if isinstance(result, list) else []

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/{method}"

    def _raise_if_failed(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except Exception:
            data = {}
        if resp.status_code == 401:
            raise RuntimeError(
                "Telegram token 無效（401）。請到 @BotFather 用 /mybots → API Token 複製新的，"
                "只貼進 D:\\Stocker\\.env 的 TELEGRAM_BOT_TOKEN。"
            )
        if resp.status_code >= 400:
            description = data.get("description") or resp.reason_phrase
            raise RuntimeError(f"Telegram 失敗（{resp.status_code}）：{description}")
        if not data.get("ok"):
            raise RuntimeError(f"Telegram 失敗: {data}")
        return data if isinstance(data, dict) else {}

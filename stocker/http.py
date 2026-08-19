from __future__ import annotations

import time
from typing import Any
import warnings

import httpx

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

from stocker.settings import Settings


class HttpClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        headers = {"User-Agent": settings.user_agent}
        timeout = httpx.Timeout(30.0)
        self._client = httpx.Client(timeout=timeout, follow_redirects=True, headers=headers)
        # 櫃買等站台憑證鏈在較新的 Python 上可能驗證失敗
        self._insecure = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
            verify=False,
        )

    def close(self) -> None:
        self._client.close()
        self._insecure.close()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._get(url, params)
        resp.raise_for_status()
        return resp.json()

    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        self._pause()
        try:
            resp = self._client.post(url, json=payload)
        except httpx.ConnectError:
            resp = self._insecure.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        resp = self._get(url, params)
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        return resp.text

    def _get(self, url: str, params: dict[str, Any] | None) -> httpx.Response:
        self._pause()
        try:
            return self._client.get(url, params=params)
        except httpx.ConnectError as exc:
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                raise
            return self._insecure.get(url, params=params)

    def _pause(self) -> None:
        time.sleep(self._settings.request_pause_sec)

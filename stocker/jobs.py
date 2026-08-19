from __future__ import annotations

import threading

from stocker.collectors.etf import fetch_etf_snapshot, select_top_etfs
from stocker.collectors.mops import fetch_material_news
from stocker.collectors.t86 import fetch_trust_flows
from stocker.db import Database
from stocker.http import HttpClient
from stocker.intelligence.digest import format_daily_digest, format_etf_detail, format_high_news
from stocker.intelligence.etf_diff import diff_holdings
from stocker.notifiers.telegram import TelegramNotifier
from stocker.settings import DEFAULT_ACTIVE_ETFS, Settings, load_settings


class StockerApp:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.db = Database(self.settings.db_path)
        self.http = HttpClient(self.settings)
        self.telegram = TelegramNotifier(self.settings)
        self._lock = threading.RLock()

    def close(self) -> None:
        self.http.close()
        self.telegram.close()

    def poll_mops(self, send_high: bool = True) -> int:
        with self._lock:
            news = fetch_material_news(self.http)
            high = [item for item in news if item.level == "high"]
            unseen_keys = set(self.db.unseen("mops", [item.key for item in high]))
            fresh = [item for item in high if item.key in unseen_keys]
            if send_high and fresh:
                self.telegram.send(format_high_news(fresh))
                for item in fresh:
                    self.db.mark_seen("mops", item.key)
            return len(fresh)

    def _collect_etfs(self) -> tuple[list, list, dict[str, str], bool, list[str]]:
        snapshots = []
        moves = []
        prev_dates: dict[str, str] = {}
        errors: list[str] = []
        etf_has_history = False
        for etf in DEFAULT_ACTIVE_ETFS:
            try:
                snap = fetch_etf_snapshot(self.http, etf)
                snapshots.append(snap)
                prev_date = self.db.previous_etf_date(snap.etf_code, snap.as_of)
                if prev_date:
                    etf_has_history = True
                    prev_dates[snap.etf_code] = prev_date
                    previous = self.db.etf_holdings(snap.etf_code, prev_date)
                    moves.extend(
                        diff_holdings(snap, previous, self.settings, prev_as_of=prev_date)
                    )
                self.db.save_etf_holdings(
                    snap.etf_code,
                    snap.etf_name,
                    snap.as_of,
                    snap.aum,
                    [
                        {
                            "stock_code": h.stock_code,
                            "stock_name": h.stock_name,
                            "shares": h.shares,
                            "weight": h.weight,
                            "market_value": h.market_value,
                        }
                        for h in snap.holdings
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{etf.code} {exc}")
        snapshots = select_top_etfs(snapshots, self.settings.etf_top_n)
        return snapshots, moves, prev_dates, etf_has_history, errors

    def daily_report(self, force: bool = False, send: bool = True) -> str:
        with self._lock:
            news = fetch_material_news(self.http)
            important = [item for item in news if item.level in {"high", "medium"}]
            as_of, flows = fetch_trust_flows(self.http)
            snapshots, moves, prev_dates, etf_has_history, errors = self._collect_etfs()
            report_date = as_of or (snapshots[0].as_of if snapshots else "unknown")
            digest_key = f"daily:{report_date}"
            text = format_daily_digest(
                report_date,
                important,
                flows,
                snapshots,
                moves,
                self.settings,
                etf_has_history=etf_has_history,
                prev_dates=prev_dates,
            )
            if errors:
                text += "\n\n⚠️ 部分 ETF 來源失敗：\n" + "\n".join(f"• {e}" for e in errors)

            already = not self.db.unseen("digest", [digest_key])
            if send and (force or not already):
                self.telegram.send(text)
                self.db.mark_seen("digest", digest_key)
            return text

    def etf_report(self, send: bool = True) -> str:
        with self._lock:
            snapshots, moves, prev_dates, etf_has_history, errors = self._collect_etfs()
            text = format_etf_detail(
                snapshots,
                moves,
                self.settings,
                etf_has_history,
                prev_dates=prev_dates,
                errors=errors,
            )
            if send:
                self.telegram.send(text)
            return text

    def send_test(self) -> None:
        self.telegram.send_menu(
            "Stocker 測試成功。可用下方按鈕立即推播，之後排程也會送到這裡。"
        )

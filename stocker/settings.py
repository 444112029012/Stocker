from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TZ_NAME = "Asia/Taipei"


@dataclass(frozen=True)
class ActiveEtf:
    code: str
    name: str
    issuer: str
    # issuer-specific lookup
    extra: dict[str, str] = field(default_factory=dict)


# 2026-08 規模前五大（可依市場變化改這份名單）
# 來源：公開規模排行（統一台股增長、統一升級50、復華未來50、統一全球創新、群益台灣強棒）
DEFAULT_ACTIVE_ETFS: tuple[ActiveEtf, ...] = (
    ActiveEtf("00981A", "主動統一台股增長", "upamc", {"fund_code": "49YTW"}),
    ActiveEtf("00403A", "主動統一升級50", "upamc", {"fund_code": "63YTW"}),
    ActiveEtf("00991A", "主動復華未來50", "fuhwa", {"fund_id": "ETF23"}),
    ActiveEtf("00988A", "主動統一全球創新", "upamc", {"fund_code": "61YTW"}),
    ActiveEtf("00982A", "主動群益台灣強棒", "capital", {"product_id": "399"}),
)


@dataclass
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    db_path: Path
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    request_pause_sec: float = 1.2
    etf_top_n: int = 5
    t86_top_n: int = 10
    news_digest_limit: int = 30
    etf_moves_per_fund: int = 15  # 每日摘要每檔買超/賣超各列幾筆
    etf_detail_per_side: int = 40  # 專用 ETF 明細每邊列幾筆
    share_change_threshold: int = 1_000  # 1 張才列入買賣超
    weight_change_threshold: float = 0.15  # 百分點（保留，持股張數未變時不列）
    consensus_min_etfs: int = 2


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip().strip('"').strip("'")
    db_raw = os.getenv("STOCKER_DB_PATH", "").strip()
    db_path = Path(db_raw) if db_raw else ROOT / "data" / "stocker.db"
    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        db_path=db_path,
    )

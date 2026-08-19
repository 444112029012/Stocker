from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    kind TEXT NOT NULL,
    item_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kind, item_key)
);

CREATE TABLE IF NOT EXISTS etf_holdings (
    etf_code TEXT NOT NULL,
    as_of TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    shares INTEGER NOT NULL,
    weight REAL NOT NULL,
    market_value REAL,
    PRIMARY KEY (etf_code, as_of, stock_code)
);

CREATE TABLE IF NOT EXISTS etf_snapshots (
    etf_code TEXT NOT NULL,
    as_of TEXT NOT NULL,
    etf_name TEXT NOT NULL,
    aum REAL,
    PRIMARY KEY (etf_code, as_of)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def mark_seen(self, kind: str, item_key: str) -> bool:
        """Return True if this is the first time we see the key."""
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO seen_items (kind, item_key) VALUES (?, ?)",
                (kind, item_key),
            )
            return cur.rowcount == 1

    def unseen(self, kind: str, keys: Sequence[str]) -> list[str]:
        if not keys:
            return []
        placeholders = ",".join("?" for _ in keys)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT item_key FROM seen_items WHERE kind = ? AND item_key IN ({placeholders})",
                (kind, *keys),
            ).fetchall()
        seen = {row["item_key"] for row in rows}
        return [key for key in keys if key not in seen]

    def save_etf_holdings(
        self,
        etf_code: str,
        etf_name: str,
        as_of: str,
        aum: float | None,
        holdings: Sequence[dict[str, Any]],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO etf_snapshots (etf_code, as_of, etf_name, aum)
                VALUES (?, ?, ?, ?)
                """,
                (etf_code, as_of, etf_name, aum),
            )
            conn.execute(
                "DELETE FROM etf_holdings WHERE etf_code = ? AND as_of = ?",
                (etf_code, as_of),
            )
            conn.executemany(
                """
                INSERT INTO etf_holdings
                    (etf_code, as_of, stock_code, stock_name, shares, weight, market_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        etf_code,
                        as_of,
                        h["stock_code"],
                        h["stock_name"],
                        int(h["shares"]),
                        float(h["weight"]),
                        h.get("market_value"),
                    )
                    for h in holdings
                ],
            )

    def previous_etf_date(self, etf_code: str, as_of: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT as_of FROM etf_snapshots
                WHERE etf_code = ? AND as_of < ?
                ORDER BY as_of DESC
                LIMIT 1
                """,
                (etf_code, as_of),
            ).fetchone()
        return row["as_of"] if row else None

    def etf_holdings(self, etf_code: str, as_of: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT stock_code, stock_name, shares, weight, market_value
                FROM etf_holdings
                WHERE etf_code = ? AND as_of = ?
                """,
                (etf_code, as_of),
            ).fetchall()
        return [dict(row) for row in rows]

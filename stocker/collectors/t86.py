from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from stocker.dates import format_roc_slash, previous_business_days, yyyymmdd
from stocker.http import HttpClient

TWSE_T86 = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_T86 = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"


@dataclass
class TrustFlow:
    market: str
    as_of: str
    stock_code: str
    stock_name: str
    buy_shares: int
    sell_shares: int
    net_shares: int

    @property
    def net_lots(self) -> int:
        return self.net_shares // 1000


def _to_int(value: object) -> int:
    text = str(value or "0").replace(",", "").strip()
    if not text or text in {"-", "--"}:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _is_listed_stock(code: str) -> bool:
    code = code.strip()
    if not code or not code[0].isdigit():
        return False
    return not code.startswith("00")
    text = str(value or "0").replace(",", "").strip()
    if not text or text in {"-", "--"}:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _parse_twse(payload: dict, as_of: str) -> list[TrustFlow]:
    fields = payload.get("fields") or []
    rows = payload.get("data") or []
    if not fields or not rows:
        return []
    index = {name: i for i, name in enumerate(fields)}

    def col(*names: str) -> int | None:
        for name in names:
            if name in index:
                return index[name]
        return None

    code_i = col("證券代號")
    name_i = col("證券名稱")
    buy_i = col("投信買進股數")
    sell_i = col("投信賣出股數")
    net_i = col("投信買賣超股數")
    if None in {code_i, name_i, net_i}:
        return []
    out: list[TrustFlow] = []
    for row in rows:
        net = _to_int(row[net_i])
        code = str(row[code_i]).strip()
        if net == 0 or not _is_listed_stock(code):
            continue
        out.append(
            TrustFlow(
                market="TWSE",
                as_of=as_of,
                stock_code=code,
                stock_name=str(row[name_i]).strip(),
                buy_shares=_to_int(row[buy_i]) if buy_i is not None else 0,
                sell_shares=_to_int(row[sell_i]) if sell_i is not None else 0,
                net_shares=net,
            )
        )
    return out


def _parse_tpex(payload: dict, as_of: str) -> list[TrustFlow]:
    tables = payload.get("tables") or []
    if not tables:
        # older shape: aaData
        rows = payload.get("aaData") or []
        fields = None
    else:
        table = tables[0]
        fields = table.get("fields")
        rows = table.get("data") or []
    out: list[TrustFlow] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 11:
            continue
        # Typical TPEx columns include 代號, 名稱, ... 投信買賣超
        code = str(row[0]).strip()
        name = str(row[1]).strip()
        if not code or not code[0].isdigit():
            continue
        # Prefer last 投信-related numeric columns; layout has 投信買進/賣出/買賣超 around index 8-10
        net = _to_int(row[10] if len(row) > 10 else 0)
        buy = _to_int(row[8] if len(row) > 8 else 0)
        sell = _to_int(row[9] if len(row) > 9 else 0)
        if fields:
            index = {name: i for i, name in enumerate(fields)}
            if "投信買賣超股數" in index:
                net = _to_int(row[index["投信買賣超股數"]])
            if "投信買進股數" in index:
                buy = _to_int(row[index["投信買進股數"]])
            if "投信賣出股數" in index:
                sell = _to_int(row[index["投信賣出股數"]])
        if net == 0 or not _is_listed_stock(code):
            continue
        out.append(
            TrustFlow(
                market="TPEX",
                as_of=as_of,
                stock_code=code,
                stock_name=name,
                buy_shares=buy,
                sell_shares=sell,
                net_shares=net,
            )
        )
    return out


def fetch_trust_flows(http: HttpClient, as_of: date | None = None) -> tuple[str, list[TrustFlow]]:
    for day in previous_business_days(6, as_of):
        twse = http.get_json(
            TWSE_T86,
            params={
                "date": yyyymmdd(day),
                "selectType": "ALLBUT0999",
                "response": "json",
            },
        )
        items = _parse_twse(twse if isinstance(twse, dict) else {}, day.isoformat())
        try:
            tpex = http.get_json(
                TPEX_T86,
                params={
                    "l": "zh-tw",
                    "o": "json",
                    "se": "EW",
                    "t": "D",
                    "d": format_roc_slash(day),
                },
            )
            if isinstance(tpex, dict):
                items.extend(_parse_tpex(tpex, day.isoformat()))
        except Exception:
            pass
        if items:
            return day.isoformat(), items
    return "", []

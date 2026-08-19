from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from stocker.dates import previous_business_days
from stocker.http import HttpClient
from stocker.settings import ActiveEtf


@dataclass
class EtfHolding:
    etf_code: str
    etf_name: str
    as_of: str
    aum: float | None
    stock_code: str
    stock_name: str
    shares: int
    weight: float
    market_value: float | None = None


@dataclass
class EtfSnapshot:
    etf_code: str
    etf_name: str
    as_of: str
    aum: float | None
    holdings: list[EtfHolding]


def _to_float(value: object) -> float:
    text = str(value or "0").replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "--"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_int(value: object) -> int:
    return int(_to_float(value))


def _clean_code(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value).upper()


def fetch_etf_snapshot(http: HttpClient, etf: ActiveEtf) -> EtfSnapshot:
    if etf.issuer == "upamc":
        return _fetch_upamc(http, etf)
    if etf.issuer == "fuhwa":
        return _fetch_fuhwa(http, etf)
    if etf.issuer == "capital":
        return _fetch_capital(http, etf)
    raise ValueError(f"Unsupported issuer: {etf.issuer}")


def _snapshot(
    etf: ActiveEtf,
    as_of: str,
    aum: float | None,
    rows: list[tuple[str, str, int, float, float | None]],
) -> EtfSnapshot:
    holdings = [
        EtfHolding(
            etf_code=etf.code,
            etf_name=etf.name,
            as_of=as_of,
            aum=aum,
            stock_code=code,
            stock_name=name,
            shares=shares,
            weight=weight,
            market_value=mv,
        )
        for code, name, shares, weight, mv in rows
        if code and shares >= 0
    ]
    return EtfSnapshot(etf.code, etf.name, as_of, aum, holdings)


def _fetch_upamc(http: HttpClient, etf: ActiveEtf) -> EtfSnapshot:
    fund_code = etf.extra["fund_code"]
    html = http.get_text(
        "https://www.ezmoney.com.tw/ETF/Fund/Info",
        params={"fundCode": fund_code},
    )
    as_of, aum, rows = _parse_upamc_data_asset(html)
    if not rows:
        as_of, aum, rows = _parse_upamc_asset_db(html)
    if not rows:
        as_of, aum, rows = _parse_upamc_tables(html)
    if not as_of or not rows:
        raise RuntimeError(f"{etf.code} 統一投信持股日期解析失敗")
    return _snapshot(etf, as_of, aum, rows)


def _parse_upamc_data_asset(html: str) -> tuple[str, float | None, list[tuple[str, str, int, float, float | None]]]:
    soup = BeautifulSoup(html, "lxml")
    node = soup.find(id="DataAsset")
    raw = node.get("data-content") if node else None
    if not raw:
        return "", None, []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "", None, []
    return _holdings_from_upamc_assets(data)


def _holdings_from_upamc_assets(data: list) -> tuple[str, float | None, list[tuple[str, str, int, float, float | None]]]:
    aum = None
    as_of = ""
    rows: list[tuple[str, str, int, float, float | None]] = []
    for item in data:
        code = item.get("AssetCode")
        if code == "NAV":
            aum = _to_float(item.get("Value"))
            as_of = _upamc_date(item.get("EditDate") or item.get("EndDate"))
        if code != "ST":
            continue
        as_of = as_of or _upamc_date(item.get("EditDate"))
        for detail in item.get("Details") or []:
            stock = _clean_code(str(detail.get("DetailCode") or ""))
            if not stock:
                continue
            as_of = as_of or _upamc_date(detail.get("TranDate") or detail.get("EditTime"))
            rows.append(
                (
                    stock,
                    str(detail.get("DetailName") or "").strip(),
                    _to_int(detail.get("Share")),
                    _to_float(detail.get("NavRate")),
                    _to_float(detail.get("Amount")) or None,
                )
            )
    return as_of, aum, rows


def _upamc_date(value: object) -> str:
    text = str(value or "").replace("/", "-")
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return ""


def _parse_upamc_asset_db(html: str) -> tuple[str, float | None, list[tuple[str, str, int, float, float | None]]]:
    match = re.search(r"assetDB\s*=\s*(\[[\s\S]*?\]);", html)
    if not match:
        return "", None, []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return "", None, []
    return _holdings_from_upamc_assets(data)


def _parse_upamc_tables(html: str) -> tuple[str, float | None, list[tuple[str, str, int, float, float | None]]]:
    soup = BeautifulSoup(html, "lxml")
    as_of = ""
    date_node = soup.find(string=re.compile(r"資料日期"))
    if date_node:
        found = re.search(r"(\d{4}/\d{2}/\d{2})", str(date_node.parent.get_text() if hasattr(date_node, "parent") else date_node))
        if found:
            as_of = found.group(1).replace("/", "-")
    aum = None
    text = soup.get_text("\n", strip=True)
    nav_match = re.search(r"淨資產\s*NTD\s*([\d,]+)", text)
    if nav_match:
        aum = _to_float(nav_match.group(1))
    rows: list[tuple[str, str, int, float, float | None]] = []
    for table in soup.find_all("table"):
        header = " ".join(th.get_text(strip=True) for th in table.find_all(["th", "td"])[:6])
        if "股票代號" not in header or "股數" not in header:
            continue
        for tr in table.find_all("tr")[1:]:
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cols) < 4:
                continue
            code = _clean_code(cols[0])
            if not code or not code[0].isdigit():
                continue
            rows.append((code, cols[1], _to_int(cols[2]), _to_float(cols[3]), None))
        if rows:
            break
    return as_of, aum, rows


def _fetch_fuhwa(http: HttpClient, etf: ActiveEtf) -> EtfSnapshot:
    fund_id = etf.extra["fund_id"]
    last_error: Exception | None = None
    for day in previous_business_days(8):
        try:
            payload = http.get_json(
                "https://www.fhtrust.com.tw/api/assets",
                params={"fundID": fund_id, "qDate": day.strftime("%Y/%m/%d")},
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        result = (payload or {}).get("result") or []
        if not result:
            continue
        block = result[0]
        details = [
            row
            for row in (block.get("detail") or [])
            if row.get("ftype") == "股票" and row.get("stockid")
        ]
        if not details:
            continue
        as_of = str(block.get("dDate") or day.isoformat()).replace("/", "-")
        aum = _to_float(block.get("pcf_FundNav"))
        rows = [
            (
                _clean_code(str(row.get("stockid"))),
                str(row.get("stockname") or "").strip(),
                _to_int(row.get("qshare")),
                _to_float(row.get("prate_addaccint")),
                _to_float(row.get("mvalue")) or None,
            )
            for row in details
        ]
        return _snapshot(etf, as_of, aum, rows)
    raise RuntimeError(f"{etf.code} 復華持股抓取失敗: {last_error}")


def _fetch_capital(http: HttpClient, etf: ActiveEtf) -> EtfSnapshot:
    payload = http.post_json(
        "https://www.capitalfund.com.tw/CFWeb/api/etf/buyback",
        {"fundId": etf.extra["product_id"], "date": None},
    )
    if payload.get("code") != 200:
        raise RuntimeError(f"{etf.code} 群益 PCF 失敗: {payload.get('message')}")
    data = payload.get("data") or {}
    pcf = data.get("pcf") or {}
    stocks = data.get("stocks") or []
    as_of = str(pcf.get("date2") or pcf.get("date1") or "").replace("/", "-")
    rows = [
        (
            _clean_code(str(row.get("stocNo"))),
            str(row.get("stocName") or "").strip(),
            _to_int(row.get("share")),
            _to_float(row.get("weight")),
            None,
        )
        for row in stocks
    ]
    return _snapshot(etf, as_of, _to_float(pcf.get("nav")), rows)


def select_top_etfs(snapshots: list[EtfSnapshot], top_n: int) -> list[EtfSnapshot]:
    ranked = sorted(snapshots, key=lambda s: s.aum or 0, reverse=True)
    return ranked[:top_n]

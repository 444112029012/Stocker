from __future__ import annotations

from dataclasses import dataclass

from stocker.dates import parse_hhmmss, roc_to_date
from stocker.http import HttpClient

TWSE_MOPS = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
TPEX_MOPS = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"


@dataclass
class MaterialNews:
    market: str
    company_code: str
    company_name: str
    spoke_date: str
    spoke_time: str
    title: str
    clause: str
    event_date: str
    detail: str
    score: int
    level: str  # high / medium / low

    @property
    def key(self) -> str:
        return f"{self.market}:{self.company_code}:{self.spoke_date}:{self.spoke_time}:{self.title}"

    @property
    def mops_url(self) -> str:
        return (
            "https://mopsplus.twse.com.tw/mops/web/t05st01"
            if self.market == "TWSE"
            else "https://mopsplus.twse.com.tw/mops/web/t05st01"
        )


HIGH_KEYWORDS = (
    "減資",
    "增資",
    "私募",
    "吸收合併",
    "合併案",
    "簡易合併",
    "與他公司合併",
    "收購",
    "分割",
    "解散",
    "重整",
    "破產",
    "停工",
    "停業",
    "火災",
    "災害",
    "重大損失",
    "庫藏股",
    "暫停交易",
    "注意股票",
    "處置",
    "董事長異動",
    "總經理異動",
    "解任",
    "辭任",
    "財務預測",
    "重編",
    "更正財報",
    "訴訟",
    "假扣押",
    "取得或處分",
    "處分資產",
    "取得資產",
    "取得有價證券",
    "處分有價證券",
    "出售子公司",
)

MEDIUM_KEYWORDS = (
    "股利",
    "配息",
    "除權",
    "除息",
    "財報",
    "財務報告",
    "自結",
    "營收",
    "法說",
    "法人說明會",
    "董事會",
    "股東會",
    "轉換公司債",
    "發行",
    "內部人",
    "持股",
    "質權",
)

LOW_SKIP_KEYWORDS = (
    "更名",
    "變更公司名稱",
    "面額變更",
    "連續公告",
)

CLARIFY_KEYWORDS = ("澄清", "說明媒體", "報載")


def _field(row: dict, *names: str) -> str:
    for name in names:
        if name in row and row[name] is not None:
            return str(row[name]).strip()
    # MOPS sometimes pads keys with trailing spaces
    for key, value in row.items():
        if key.strip() in names and value is not None:
            return str(value).strip()
    return ""


def score_news(title: str, clause: str, detail: str) -> tuple[int, str]:
    if any(k in title for k in LOW_SKIP_KEYWORDS) and "第51款" in clause:
        return 0, "low"
    if any(k in title for k in CLARIFY_KEYWORDS):
        return 1, "low"
    if any(k in title for k in HIGH_KEYWORDS):
        return 80, "high"
    if any(k in title for k in MEDIUM_KEYWORDS):
        return 40, "medium"
    if clause and clause not in {"第51款", "第12款"}:
        return 25, "medium"
    return 10, "low"


def _parse_rows(rows: list[dict], market: str) -> list[MaterialNews]:
    items: list[MaterialNews] = []
    for row in rows:
        title = _field(row, "主旨", "主旨 ")
        code = _field(row, "公司代號")
        if not title or not code:
            continue
        spoke = roc_to_date(_field(row, "發言日期"))
        event = roc_to_date(_field(row, "事實發生日"))
        clause = _field(row, "符合條款")
        detail = _field(row, "說明")
        score, level = score_news(title, clause, detail)
        items.append(
            MaterialNews(
                market=market,
                company_code=code,
                company_name=_field(row, "公司名稱"),
                spoke_date=spoke.isoformat() if spoke else "",
                spoke_time=parse_hhmmss(_field(row, "發言時間")),
                title=" ".join(title.split()),
                clause=clause,
                event_date=event.isoformat() if event else "",
                detail=detail,
                score=score,
                level=level,
            )
        )
    return items


def fetch_material_news(http: HttpClient) -> list[MaterialNews]:
    items: list[MaterialNews] = []
    twse = http.get_json(TWSE_MOPS)
    items.extend(_parse_rows(twse if isinstance(twse, list) else [], "TWSE"))
    try:
        tpex = http.get_json(TPEX_MOPS)
        items.extend(_parse_rows(tpex if isinstance(tpex, list) else [], "TPEX"))
    except Exception:
        pass
    items.sort(key=lambda x: (x.spoke_date, x.spoke_time, x.score), reverse=True)
    return items

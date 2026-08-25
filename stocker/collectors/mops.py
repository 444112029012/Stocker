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
    level: str  # alert / high / medium / low
    event_type: str = ""
    impact: str = "中性"  # 利多 / 利空 / 中性
    impact_reason: str = ""

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


# 盤中立刻推：罕見、市場會重新定價的事件
ALERT_KEYWORDS = (
    ("停工", "停工"),
    ("停業", "停業"),
    ("重整", "重整"),
    ("破產", "破產"),
    ("解散", "解散"),
    ("私募", "私募"),
    ("火災", "災害"),
    ("災害", "災害"),
    ("重大損失", "重大損失"),
    ("暫停交易", "交易處置"),
    ("注意股票", "交易處置"),
    ("董事長異動", "董總"),
    ("總經理異動", "董總"),
    ("吸收合併", "併購"),
    ("合併案", "併購"),
    ("簡易合併", "併購"),
    ("與他公司合併", "併購"),
    ("收購", "併購"),
    ("減資", "減資"),
)

# 每日摘要可列、但不每 20 分鐘推
HIGH_KEYWORDS = (
    ("增資", "增資"),
    ("分割", "分割"),
    ("庫藏股", "庫藏股"),
    ("財務預測", "財測"),
    ("重編", "財報更正"),
    ("更正財報", "財報更正"),
    ("訴訟", "訴訟"),
    ("假扣押", "訴訟"),
    ("取得或處分", "資產"),
    ("處分資產", "資產"),
    ("取得資產", "資產"),
    ("取得有價證券", "資產"),
    ("處分有價證券", "資產"),
    ("出售子公司", "資產"),
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


def _match_type(title: str, rules: tuple[tuple[str, str], ...]) -> str:
    for keyword, event_type in rules:
        if keyword in title:
            return event_type
    return ""


def classify_news(title: str, clause: str) -> tuple[int, str, str]:
    if any(k in title for k in LOW_SKIP_KEYWORDS) and "第51款" in clause:
        return 0, "low", "例行"
    if any(k in title for k in CLARIFY_KEYWORDS):
        return 1, "low", "澄清"
    if "限制員工權利新股" in title and "減資" in title:
        return 10, "low", "例行減資"
    if ("董事長" in title or "總經理" in title) and ("解任" in title or "辭任" in title or "異動" in title):
        return 90, "alert", "董總"
    event = _match_type(title, ALERT_KEYWORDS)
    if event:
        return 90, "alert", event
    event = _match_type(title, HIGH_KEYWORDS)
    if event:
        return 70, "high", event
    if any(k in title for k in MEDIUM_KEYWORDS):
        return 40, "medium", "例行"
    return 10, "low", "其他"


def judge_impact(event_type: str, title: str) -> tuple[str, str]:
    """規則標籤，不是對股價的保證。"""
    if event_type == "減資":
        if "現金減資" in title:
            return "利多", "退還現金給股東"
        if "彌補虧損" in title:
            return "利空", "虧損減資"
        return "中性", "資本結構調整"
    if event_type == "增資":
        if "盈餘轉增資" in title or "資本公積" in title:
            return "中性", "帳上轉增資、不募新錢"
        return "利空", "現金增資、股本稀釋"
    if event_type == "私募":
        return "利空", "折價發行、稀釋舊股東"
    if event_type == "停工":
        return "利空", "產能或營運中斷"
    if event_type == "停業":
        return "利空", "暫停營業"
    if event_type in {"重整", "破產", "解散"}:
        return "利空", "存續或清償風險"
    if event_type == "災害":
        return "利空", "意外損失"
    if event_type == "重大損失":
        return "利空", "已實現重大損失"
    if event_type == "交易處置":
        return "利空", "流動性下降、交易受限"
    if event_type == "董總":
        if "辭任" in title or "解任" in title:
            return "利空", "經營權不確定"
        return "中性", "人事異動"
    if event_type == "併購":
        if "被收購" in title or "被合併" in title:
            return "利多", "被買方溢價收購的機率"
        return "中性", "對買賣雙方影響不同"
    if event_type == "庫藏股":
        return "利多", "買回自家股票、支撐股價"
    if event_type == "訴訟":
        return "利空", "法律或假扣押風險"
    if event_type == "財報更正":
        return "利空", "財報可信度下降"
    if event_type == "財測":
        return "中性", "需看財測上修或下修"
    if event_type == "分割":
        return "中性", "組織重組"
    if event_type == "資產":
        if "出售" in title or "處分" in title:
            return "中性", "處分資產、看價金與損益"
        return "中性", "取得資產、看代價是否合理"
    return "中性", "資訊揭露"


def score_news(title: str, clause: str, detail: str) -> tuple[int, str]:
    score, level, _event = classify_news(title, clause)
    return score, level


def collapse_similar(items: list[MaterialNews]) -> tuple[list[MaterialNews], list[MaterialNews]]:
    """同一公司、同一類事件只留分數最高且最新的一則。"""
    groups: dict[tuple[str, str], list[MaterialNews]] = {}
    for item in items:
        groups.setdefault((item.company_code, item.event_type or "其他"), []).append(item)
    kept: list[MaterialNews] = []
    dropped: list[MaterialNews] = []
    for group in groups.values():
        group.sort(key=lambda x: (x.score, x.spoke_date, x.spoke_time), reverse=True)
        kept.append(group[0])
        dropped.extend(group[1:])
    kept.sort(key=lambda x: (x.score, x.spoke_date, x.spoke_time), reverse=True)
    return kept, dropped


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
        score, level, event_type = classify_news(title, clause)
        impact, impact_reason = judge_impact(event_type, title)
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
                event_type=event_type,
                impact=impact,
                impact_reason=impact_reason,
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

from __future__ import annotations

from collections import defaultdict

from stocker.collectors.etf import EtfSnapshot
from stocker.collectors.mops import MaterialNews
from stocker.collectors.t86 import TrustFlow
from stocker.intelligence.etf_diff import HoldingMove, consensus_moves
from stocker.settings import Settings


TELEGRAM_LIMIT = 3900


def _qty(shares: int) -> str:
    sign = "+" if shares > 0 else ""
    if abs(shares) >= 1000:
        lots = shares / 1000
        if shares % 1000 == 0:
            return f"{sign}{shares // 1000:,} 張"
        return f"{sign}{lots:,.1f} 張"
    return f"{sign}{shares:,} 股"


def _lots(shares: int) -> str:
    return _qty(shares)


def _comparison_dates(
    snapshots: list[EtfSnapshot],
    prev_dates: dict[str, str],
) -> list[str]:
    pairs: list[tuple[str, str, str]] = []
    for snap in snapshots:
        prev = prev_dates.get(snap.etf_code, "")
        if prev and snap.as_of:
            pairs.append((snap.etf_code, prev, snap.as_of))
    if not pairs:
        return ["比較期間：尚無兩個交易日可對照"]
    unique = {(prev, curr) for _code, prev, curr in pairs}
    if len(unique) == 1:
        prev, curr = next(iter(unique))
        return [f"比較期間：{prev} → {curr}"]
    lines = ["比較期間（各檔資料日）："]
    for code, prev, curr in pairs:
        lines.append(f"  {code}  {prev} → {curr}")
    return lines


def format_etf_flow_section(
    snapshots: list[EtfSnapshot],
    moves: list[HoldingMove],
    settings: Settings,
    etf_has_history: bool,
    prev_dates: dict[str, str] | None = None,
    per_side: int | None = None,
    title: str = "【主動式 ETF 共識排行】",
) -> list[str]:
    prev_dates = prev_dates or {}
    limit = settings.etf_consensus_limit if per_side is None else per_side
    lines = [title]

    if not snapshots:
        lines.append("持股資料尚未取得")
        return lines
    if not etf_has_history:
        lines.append("已寫入今日持股基準，下一個交易日才會出現共識排行")
        for snap in snapshots:
            aum = f"{snap.aum / 1e8:.0f} 億" if snap.aum else "—"
            lines.append(
                f"  {snap.etf_code} {snap.etf_name}｜規模 {aum}｜持股 {len(snap.holdings)} 檔｜資料日 {snap.as_of}"
            )
        return lines

    lines.extend(_comparison_dates(snapshots, prev_dates))
    covered = "、".join(f"{s.etf_code}" for s in snapshots)
    lines.append(f"涵蓋：{covered}")
    lines.append(f"至少 {settings.consensus_min_etfs} 檔同步加減碼才列入，依同步檔數排序")

    consensus = consensus_moves(moves, settings.consensus_min_etfs)
    if not consensus:
        lines.append("本期沒有達到門檻的共識訊號")
        return lines

    by_count: dict[int, list[tuple]] = defaultdict(list)
    for row in consensus:
        by_count[len(row[3])].append(row)

    shown = 0
    leftover = 0
    for count in sorted(by_count, reverse=True):
        group = by_count[count]
        buys = [r for r in group if r[0] == "buy"]
        sells = [r for r in group if r[0] == "sell"]
        rows = buys + sells
        if shown >= limit:
            leftover += len(rows)
            continue
        lines.append("")
        lines.append(f"■ {count} 檔同步（加碼 {len(buys)}／減碼 {len(sells)}）")
        for rank, (side, code, name, etfs, net) in enumerate(rows, start=1):
            if shown >= limit:
                leftover += len(rows) - rank + 1
                break
            label = "加碼" if side == "buy" else "減碼"
            lines.append(
                f"{rank}. {label} {code} {name}  {_qty(net)}｜{', '.join(etfs)}"
            )
            shown += 1
    if leftover:
        lines.append(f"…另有 {leftover} 檔未列出，避免洗頻")
    return lines


def format_high_news(items: list[MaterialNews], limit: int = 12) -> str:
    if not items:
        return ""
    lines = ["🔥 重要重大訊息"]
    for item in items[:limit]:
        lines.append(f"• {item.company_code} {item.company_name}")
        lines.append(f"  {item.title}")
        lines.append(f"  {item.spoke_date} {item.spoke_time}｜{item.clause}")
    if len(items) > limit:
        lines.append(f"…另有 {len(items) - limit} 則，見每日摘要")
    lines.append("來源：公開資訊觀測站 OpenAPI，非正式投資建議")
    return "\n".join(lines)


def format_daily_digest(
    as_of: str,
    news: list[MaterialNews],
    flows: list[TrustFlow],
    snapshots: list[EtfSnapshot],
    moves: list[HoldingMove],
    settings: Settings,
    etf_has_history: bool = True,
    prev_dates: dict[str, str] | None = None,
) -> str:
    lines = [f"📊 Stocker 每日情報 {as_of}", ""]

    high = [n for n in news if n.level == "high"]
    medium = [n for n in news if n.level == "medium"]
    lines.append(f"【重大訊息】高 {len(high)}／中 {len(medium)}")
    shown = sorted(news, key=lambda n: n.score, reverse=True)[: settings.news_digest_limit]
    if not shown:
        lines.append("今日無符合篩選的重要訊息")
    for item in shown:
        mark = "🔥" if item.level == "high" else "•"
        lines.append(f"{mark} {item.company_code} {item.company_name}｜{item.title}")
    lines.append("")

    buys = sorted((f for f in flows if f.net_shares > 0), key=lambda f: f.net_shares, reverse=True)
    sells = sorted((f for f in flows if f.net_shares < 0), key=lambda f: f.net_shares)
    lines.append("【投信買賣超】上市+上櫃合計")
    if not flows:
        lines.append("尚無今日資料（通常約 16:00–17:00 更新）")
    else:
        lines.append("買超 Top")
        for flow in buys[: settings.t86_top_n]:
            lines.append(f"  {flow.stock_code} {flow.stock_name} {_lots(flow.net_shares)}")
        lines.append("賣超 Top")
        for flow in sells[: settings.t86_top_n]:
            lines.append(f"  {flow.stock_code} {flow.stock_name} {_lots(flow.net_shares)}")
    lines.append("")

    lines.extend(
        format_etf_flow_section(
            snapshots,
            moves,
            settings,
            etf_has_history,
            prev_dates=prev_dates,
            per_side=settings.etf_consensus_limit,
        )
    )
    lines.append("")
    lines.append("資料來自證交所/櫃買 OpenAPI 與投信公開持股，非正式投資建議。")
    return "\n".join(lines)


def format_etf_detail(
    snapshots: list[EtfSnapshot],
    moves: list[HoldingMove],
    settings: Settings,
    etf_has_history: bool,
    prev_dates: dict[str, str] | None = None,
    errors: list[str] | None = None,
) -> str:
    as_of = snapshots[0].as_of if snapshots else ""
    lines = [f"📈 主動式 ETF 共識排行 {as_of}", ""]
    lines.extend(
        format_etf_flow_section(
            snapshots,
            moves,
            settings,
            etf_has_history,
            prev_dates=prev_dates,
            per_side=settings.etf_consensus_limit,
        )
    )
    if errors:
        lines.append("")
        lines.append("⚠️ 部分 ETF 來源失敗：")
        lines.extend(f"• {e}" for e in errors)
    lines.append("")
    lines.append("張數為兩個持股日快照相減，非正式成交明細。")
    return "\n".join(lines)


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        extra = len(line) + 1
        if current and size + extra > limit:
            chunks.append("\n".join(current))
            current = [line]
            size = extra
        else:
            current.append(line)
            size += extra
    if current:
        chunks.append("\n".join(current))
    return chunks

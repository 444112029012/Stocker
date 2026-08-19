from __future__ import annotations

from collections import defaultdict

from stocker.collectors.etf import EtfSnapshot
from stocker.collectors.mops import MaterialNews
from stocker.collectors.t86 import TrustFlow
from stocker.intelligence.etf_diff import HoldingMove, aggregate_flows, consensus_moves
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


def _move_line(move: HoldingMove) -> str:
    tag = ""
    if move.action == "new":
        tag = " 新進"
    elif move.action == "exit":
        tag = " 出清"
    return (
        f"  {move.stock_code} {move.stock_name}  {_qty(move.delta_shares)}  "
        f"{move.prev_weight:.2f}%→{move.weight:.2f}%{tag}"
    )


def _split_sides(moves: list[HoldingMove]) -> tuple[list[HoldingMove], list[HoldingMove]]:
    buys = sorted(
        (m for m in moves if m.delta_shares > 0),
        key=lambda m: m.delta_shares,
        reverse=True,
    )
    sells = sorted(
        (m for m in moves if m.delta_shares < 0),
        key=lambda m: m.delta_shares,
    )
    return buys, sells


def format_etf_flow_section(
    snapshots: list[EtfSnapshot],
    moves: list[HoldingMove],
    settings: Settings,
    etf_has_history: bool,
    prev_dates: dict[str, str] | None = None,
    per_side: int | None = None,
    title: str = "【主動式 ETF 規模前五大】買賣超明細",
) -> list[str]:
    prev_dates = prev_dates or {}
    limit = settings.etf_moves_per_fund if per_side is None else per_side
    lines = [title]
    by_etf: dict[str, list[HoldingMove]] = defaultdict(list)
    for move in moves:
        by_etf[move.etf_code].append(move)

    if not snapshots:
        lines.append("持股資料尚未取得")
        return lines
    if not etf_has_history:
        lines.append("已寫入今日持股基準，下一個交易日才會出現買賣超明細")
        for snap in snapshots:
            aum = f"{snap.aum / 1e8:.0f} 億" if snap.aum else "—"
            lines.append(
                f"  {snap.etf_code} {snap.etf_name}｜規模 {aum}｜持股 {len(snap.holdings)} 檔｜資料日 {snap.as_of}"
            )
        return lines

    for snap in snapshots:
        aum = f"{snap.aum / 1e8:.0f} 億" if snap.aum else "—"
        prev = prev_dates.get(snap.etf_code) or (by_etf[snap.etf_code][0].prev_as_of if by_etf[snap.etf_code] else "")
        date_range = f"{prev}→{snap.as_of}" if prev else snap.as_of
        lines.append(f"{snap.etf_code} {snap.etf_name}｜規模 {aum}｜{date_range}")
        fund_moves = by_etf.get(snap.etf_code, [])
        buys, sells = _split_sides(fund_moves)
        if not fund_moves:
            lines.append("  無超過 1 張的持股增減")
            continue
        lines.append(f"買超 {len(buys)} 檔")
        for move in buys[:limit]:
            lines.append(_move_line(move))
        if len(buys) > limit:
            lines.append(f"  …另有 {len(buys) - limit} 檔買超")
        lines.append(f"賣超 {len(sells)} 檔")
        for move in sells[:limit]:
            lines.append(_move_line(move))
        if len(sells) > limit:
            lines.append(f"  …另有 {len(sells) - limit} 檔賣超")

    agg = aggregate_flows(moves)
    agg_buys = [r for r in agg if r[0] == "buy"]
    agg_sells = [r for r in agg if r[0] == "sell"]
    lines.append("")
    lines.append("【主動ETF合計買賣超】五檔張數加總")
    if not agg:
        lines.append("無")
    else:
        lines.append("買超")
        for _side, code, name, net, etfs in agg_buys[:limit]:
            lines.append(f"  {code} {name}  {_qty(net)}｜{', '.join(etfs)}")
        if len(agg_buys) > limit:
            lines.append(f"  …另有 {len(agg_buys) - limit} 檔")
        lines.append("賣超")
        for _side, code, name, net, etfs in agg_sells[:limit]:
            lines.append(f"  {code} {name}  {_qty(net)}｜{', '.join(etfs)}")
        if len(agg_sells) > limit:
            lines.append(f"  …另有 {len(agg_sells) - limit} 檔")

    consensus = consensus_moves(moves, settings.consensus_min_etfs)
    lines.append("")
    lines.append(f"【共識訊號】至少 {settings.consensus_min_etfs} 檔同時加減碼")
    if not consensus:
        lines.append("無")
    else:
        for side, code, name, etfs, net in consensus[:10]:
            label = "同步加碼" if side == "buy" else "同步減碼"
            lines.append(f"  {label} {code} {name}  {_qty(net)}｜{', '.join(etfs)}")
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
            per_side=settings.etf_moves_per_fund,
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
    lines = [f"📈 主動式 ETF 買賣超明細 {as_of}", ""]
    lines.extend(
        format_etf_flow_section(
            snapshots,
            moves,
            settings,
            etf_has_history,
            prev_dates=prev_dates,
            per_side=settings.etf_detail_per_side,
        )
    )
    if errors:
        lines.append("")
        lines.append("⚠️ 部分 ETF 來源失敗：")
        lines.extend(f"• {e}" for e in errors)
    lines.append("")
    lines.append("張數為前後兩個持股日快照差異，非正式成交明細。")
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

from __future__ import annotations

from collections import defaultdict

from stocker.collectors.etf import EtfSnapshot
from stocker.collectors.mops import MaterialNews
from stocker.collectors.t86 import TrustFlow
from stocker.intelligence.etf_diff import HoldingMove, consensus_moves, top_weight_moves
from stocker.settings import Settings


TELEGRAM_LIMIT = 3900

SIDE_ICON = {
    "buy": "🟢",
    "sell": "🔴",
    "increase": "🟢",
    "decrease": "🔴",
    "new": "🆕",
    "exit": "⚪",
    "加碼": "🟢",
    "減碼": "🔴",
    "新進": "🆕",
    "出清": "⚪",
}
PAIR_ICON = {"同向": "✅", "背離": "⚠️", "對照": "▫️"}


def _side_icon(side: str) -> str:
    return SIDE_ICON.get(side, "▫️")


def _etf_legend() -> str:
    return "🟢加碼　🔴減碼　🆕新進　⚪出清"


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
        return [f"📅 比較期間  {prev} → {curr}"]
    lines = ["📅 比較期間（各檔資料日）"]
    for code, prev, curr in pairs:
        lines.append(f"{code}  {prev} → {curr}")
    return lines


def format_etf_flow_section(
    snapshots: list[EtfSnapshot],
    moves: list[HoldingMove],
    settings: Settings,
    etf_has_history: bool,
    prev_dates: dict[str, str] | None = None,
    per_side: int | None = None,
    title: str = "【主動式 ETF 共識排行】",
    news: list[MaterialNews] | None = None,
) -> list[str]:
    prev_dates = prev_dates or {}
    limit = settings.etf_consensus_limit if per_side is None else per_side
    lines = [title, _etf_legend(), ""]

    if not snapshots:
        lines.append("持股資料尚未取得")
        return lines
    if not etf_has_history:
        lines.append("已寫入今日持股基準，下一個交易日才會出現共識排行")
        for snap in snapshots:
            aum = f"{snap.aum / 1e8:.0f} 億" if snap.aum else "—"
            lines.append("")
            lines.append(f"{snap.etf_code} {snap.etf_name}")
            lines.append(f"規模 {aum}｜持股 {len(snap.holdings)} 檔｜資料日 {snap.as_of}")
        return lines

    lines.extend(_comparison_dates(snapshots, prev_dates))
    covered = "、".join(s.etf_code for s in snapshots)
    lines.append(f"涵蓋 {covered}")
    lines.append(f"至少 {settings.consensus_min_etfs} 檔同步才列入")

    consensus = consensus_moves(moves, settings.consensus_min_etfs)
    if consensus:
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
            lines.append(f"📌 {count} 檔同步")
            lines.append(f"{_side_icon('buy')}加碼 {len(buys)}　{_side_icon('sell')}減碼 {len(sells)}")
            for rank, (side, code, name, etfs, net) in enumerate(rows, start=1):
                if shown >= limit:
                    leftover += len(rows) - rank + 1
                    break
                icon = _side_icon(side)
                label = "加碼" if side == "buy" else "減碼"
                lines.append("")
                lines.append(f"{rank}. {icon} {label}  {code} {name}")
                lines.append(f"{_qty(net)}")
                lines.append("、".join(etfs))
                shown += 1
        if leftover:
            lines.append(f"…另有 {leftover} 檔未列出，避免洗頻")
    else:
        lines.append("")
        lines.append("本期沒有 2 檔以上同步加減碼，改列權重變化最大的個股")
        fallback = top_weight_moves(
            moves,
            settings.etf_fallback_min_weight,
            settings.etf_fallback_limit,
        )
        if not fallback:
            lines.append(f"也沒有超過 {settings.etf_fallback_min_weight:.1f} 個百分點的權重變化")
        else:
            lines.append(
                f"門檻：權重變化 ≥ {settings.etf_fallback_min_weight:.1f} 個百分點，或新進／出清"
            )
            for rank, move in enumerate(fallback, start=1):
                label = {"new": "新進", "exit": "出清", "increase": "加碼", "decrease": "減碼"}.get(
                    move.action, "調整"
                )
                icon = _side_icon(move.action)
                lines.append("")
                lines.append(f"{rank}. {icon} {label}  {move.stock_code} {move.stock_name}")
                lines.append(
                    f"{move.prev_weight:.2f}% → {move.weight:.2f}%（{move.delta_weight:+.2f}%）"
                )
                lines.append(f"{_qty(move.delta_shares)}｜{move.etf_code}")
    lines.extend(_format_news_etf_pairs(moves, news or [], settings))
    return lines


IMPACT_ICON = {"利空": "🔴", "利多": "🟢", "中性": "⚪"}


def _format_news_etf_pairs(
    moves: list[HoldingMove],
    news: list[MaterialNews],
    settings: Settings,
) -> list[str]:
    if not moves or not news:
        return []
    news_by_code: dict[str, list[MaterialNews]] = defaultdict(list)
    for item in news:
        news_by_code[item.company_code].append(item)
    moves_by_code: dict[str, list[HoldingMove]] = defaultdict(list)
    for move in moves:
        moves_by_code[move.stock_code].append(move)

    rows: list[tuple[str, MaterialNews, str, str, str, int, list[str]]] = []
    for code, fund_moves in moves_by_code.items():
        hits = news_by_code.get(code)
        if not hits:
            continue
        net = sum(m.delta_shares for m in fund_moves)
        if net == 0:
            continue
        headline = sorted(hits, key=_impact_sort_key)[0]
        etfs = sorted({m.etf_code for m in fund_moves})
        side = "加碼" if net > 0 else "減碼"
        if headline.impact == "利多" and net > 0:
            tag = "同向"
        elif headline.impact == "利空" and net < 0:
            tag = "同向"
        elif headline.impact in {"利多", "利空"}:
            tag = "背離"
        else:
            tag = "對照"
        rows.append((tag, headline, side, code, fund_moves[0].stock_name, net, etfs))

    if not rows:
        return ["", "【重訊 × ETF】", "本期沒有個股同時出現重訊與持股變化"]

    tag_rank = {"同向": 0, "背離": 1, "對照": 2}
    rows.sort(key=lambda r: (tag_rank.get(r[0], 9), -len(r[6]), -abs(r[5])))
    shown = rows[: settings.etf_news_pair_limit]
    lines = ["", "【重訊 × ETF】", "✅同向　⚠️背離　▫️對照", ""]
    for tag, headline, side, code, name, net, etfs in shown:
        news_icon = IMPACT_ICON.get(headline.impact, "⚪")
        side_icon = _side_icon(side)
        lines.append(f"{PAIR_ICON.get(tag, '▫️')} {tag}")
        lines.append(f"{news_icon} {headline.impact}  {code} {name}｜{headline.event_type}")
        lines.append(f"{side_icon} ETF {side} {len(etfs)} 檔  {_qty(net)}")
        lines.append("、".join(etfs))
        lines.append("")
    leftover = len(rows) - len(shown)
    if leftover:
        lines.append(f"…另有 {leftover} 檔交叉未列出")
    return lines


def _impact_sort_key(item: MaterialNews) -> tuple:
    order = {"利空": 0, "利多": 1, "中性": 2}
    return (order.get(item.impact, 9), -item.score, item.spoke_date, item.spoke_time)


def _short_title(title: str, limit: int = 36) -> str:
    text = title
    for noise in ("公告", "本公司"):
        text = text.replace(noise, "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _news_block(item: MaterialNews) -> str:
    icon = IMPACT_ICON.get(item.impact, "⚪")
    return "\n".join(
        [
            f"{icon} {item.impact}  {item.company_code} {item.company_name}",
            f"{item.event_type or '重訊'}｜{item.impact_reason}",
            _short_title(item.title),
        ]
    )


def _news_compact(item: MaterialNews) -> str:
    icon = IMPACT_ICON.get(item.impact, "⚪")
    return (
        f"{icon} {item.impact}  {item.company_code} {item.company_name}"
        f"｜{item.event_type or '重訊'}"
    )


def _append_news_list(lines: list[str], items: list[MaterialNews], featured_limit: int) -> None:
    ranked = sorted(items, key=_impact_sort_key)
    featured = ranked[:featured_limit]
    rest = ranked[featured_limit:]
    if not ranked:
        lines.append("今日無減資、停工、私募、併購、增資等需立即注意的訊息")
        return
    for item in featured:
        lines.append("")
        lines.append(_news_block(item))
    if rest:
        lines.append("")
        lines.append(f"【其餘 {len(rest)} 則】改為一行，避免洗頻但仍全部列出")
        for item in rest:
            lines.append(_news_compact(item))


def format_high_news(items: list[MaterialNews], limit: int = 8, leftover: int = 0) -> str:
    if not items:
        return ""
    ranked = sorted(items, key=_impact_sort_key)
    lines = [
        f"盤中重訊 {len(ranked)} 則",
        "🔴利空　🟢利多　⚪中性（規則標籤）",
    ]
    _append_news_list(lines, ranked, limit)
    return "\n".join(lines).rstrip()


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

    lines.append(f"【重大訊息】{len(news)} 則")
    lines.append("🔴利空　🟢利多　⚪中性（財報／董事會未列入）")
    _append_news_list(lines, news, settings.news_digest_limit)
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
            news=news,
        )
    )
    lines.append("")
    lines.append("資料來自證交所/櫃買 OpenAPI 與投信公開持股。利多／利空為規則標籤，非正式投資建議。")
    return "\n".join(lines)


def format_etf_detail(
    snapshots: list[EtfSnapshot],
    moves: list[HoldingMove],
    settings: Settings,
    etf_has_history: bool,
    prev_dates: dict[str, str] | None = None,
    errors: list[str] | None = None,
    news: list[MaterialNews] | None = None,
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
            news=news,
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

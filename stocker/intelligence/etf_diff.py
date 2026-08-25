from __future__ import annotations

from stocker.collectors.etf import EtfHolding, EtfSnapshot
from stocker.settings import Settings


class HoldingMove:
    __slots__ = (
        "etf_code",
        "etf_name",
        "stock_code",
        "stock_name",
        "action",
        "prev_shares",
        "shares",
        "delta_shares",
        "prev_weight",
        "weight",
        "delta_weight",
        "prev_as_of",
    )

    def __init__(
        self,
        etf_code: str,
        etf_name: str,
        stock_code: str,
        stock_name: str,
        action: str,
        prev_shares: int,
        shares: int,
        delta_shares: int,
        prev_weight: float,
        weight: float,
        delta_weight: float,
        prev_as_of: str = "",
    ) -> None:
        self.etf_code = etf_code
        self.etf_name = etf_name
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.action = action
        self.prev_shares = prev_shares
        self.shares = shares
        self.delta_shares = delta_shares
        self.prev_weight = prev_weight
        self.weight = weight
        self.delta_weight = delta_weight
        self.prev_as_of = prev_as_of

    @property
    def delta_lots(self) -> int:
        return self.delta_shares // 1000


def _row(item: EtfHolding | dict) -> dict:
    if isinstance(item, dict):
        return item
    return {
        "stock_code": item.stock_code,
        "stock_name": item.stock_name,
        "shares": item.shares,
        "weight": item.weight,
    }


def _move(
    current: EtfSnapshot,
    action: str,
    stock_code: str,
    stock_name: str,
    prev_shares: int,
    shares: int,
    prev_weight: float,
    weight: float,
    prev_as_of: str,
) -> HoldingMove:
    return HoldingMove(
        current.etf_code,
        current.etf_name,
        stock_code,
        stock_name,
        action,
        prev_shares,
        shares,
        shares - prev_shares,
        prev_weight,
        weight,
        weight - prev_weight,
        prev_as_of,
    )


def diff_holdings(
    current: EtfSnapshot,
    previous: list[EtfHolding] | list[dict],
    settings: Settings,
    prev_as_of: str = "",
) -> list[HoldingMove]:
    prev_map = {_row(h)["stock_code"]: _row(h) for h in previous}
    curr_map = {h.stock_code: h for h in current.holdings}
    moves: list[HoldingMove] = []
    min_shares = settings.share_change_threshold

    for code, holding in curr_map.items():
        old = prev_map.get(code)
        if old is None:
            if holding.shares <= 0:
                continue
            moves.append(
                _move(
                    current,
                    "new",
                    holding.stock_code,
                    holding.stock_name,
                    0,
                    holding.shares,
                    0.0,
                    holding.weight,
                    prev_as_of,
                )
            )
            continue
        old_shares = int(old["shares"])
        delta_shares = holding.shares - old_shares
        if delta_shares == 0 or abs(delta_shares) < min_shares:
            continue
        action = "increase" if delta_shares > 0 else "decrease"
        moves.append(
            _move(
                current,
                action,
                holding.stock_code,
                holding.stock_name,
                old_shares,
                holding.shares,
                float(old["weight"]),
                holding.weight,
                prev_as_of,
            )
        )

    for code, old in prev_map.items():
        if code in curr_map:
            continue
        old_shares = int(old["shares"])
        if old_shares <= 0:
            continue
        moves.append(
            _move(
                current,
                "exit",
                code,
                str(old["stock_name"]),
                old_shares,
                0,
                float(old["weight"]),
                0.0,
                prev_as_of,
            )
        )

    moves.sort(key=lambda m: abs(m.delta_shares), reverse=True)
    return moves


def aggregate_flows(
    all_moves: list[HoldingMove],
) -> list[tuple[str, str, str, int, list[str]]]:
    """Stock-level net lots across ETFs: (side, code, name, net_shares, etf_codes)."""
    grouped: dict[str, list[HoldingMove]] = {}
    for move in all_moves:
        grouped.setdefault(move.stock_code, []).append(move)
    rows: list[tuple[str, str, str, int, list[str]]] = []
    for code, items in grouped.items():
        net = sum(m.delta_shares for m in items)
        if net == 0:
            continue
        etfs = sorted({m.etf_code for m in items if m.delta_shares != 0})
        side = "buy" if net > 0 else "sell"
        rows.append((side, code, items[0].stock_name, net, etfs))
    rows.sort(key=lambda r: abs(r[3]), reverse=True)
    return rows


def consensus_moves(
    all_moves: list[HoldingMove], min_etfs: int
) -> list[tuple[str, str, str, list[str], int]]:
    grouped: dict[tuple[str, str], list[HoldingMove]] = {}
    for move in all_moves:
        side = "buy" if move.action in {"new", "increase"} else "sell"
        grouped.setdefault((side, move.stock_code), []).append(move)
    rows: list[tuple[str, str, str, list[str], int]] = []
    for (side, code), items in grouped.items():
        etfs = sorted({m.etf_code for m in items})
        if len(etfs) < min_etfs:
            continue
        net = sum(m.delta_shares for m in items)
        rows.append((side, code, items[0].stock_name, etfs, net))
    rows.sort(key=lambda r: (-len(r[3]), -abs(r[4])))
    return rows


def top_weight_moves(
    all_moves: list[HoldingMove],
    min_abs_weight: float,
    limit: int,
) -> list[HoldingMove]:
    ranked = [
        move
        for move in all_moves
        if abs(move.delta_weight) >= min_abs_weight or move.action in {"new", "exit"}
    ]
    ranked.sort(key=lambda m: (abs(m.delta_weight), abs(m.delta_shares)), reverse=True)
    return ranked[:limit]

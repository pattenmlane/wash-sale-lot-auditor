"""The lot-level ledger: lots split only where a sale or a match cuts them (the verifier replays share by share)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from contract import Match, SaleResult, Side, SoldLot, Trade
from verifier.rules import WINDOW


@dataclass(eq=False)
class Lot:
    buy_id: str
    ticker: str
    day: int
    shares: int
    basis: int
    absorbed: bool = False


def _front(lots: list[Lot], lot: Lot, shares: int) -> Lot:
    """Cuts the first shares off a lot, as a lot of their own just ahead of it."""
    front = replace(lot, shares=shares)
    lot.shares -= shares
    lots.insert(lots.index(lot), front)
    return front


def _sell(lots: list[Lot], sale: Trade) -> list[Lot]:
    sold, left = [], sale.shares
    while left:
        held = (lot for lot in lots if lot.ticker == sale.ticker and lot.day < sale.day and lot.shares)
        lot = next(held, None)
        if lot is None:
            raise ValueError(f"sale {sale.id} sells more {sale.ticker} than is held")
        front = _front(lots, lot, min(left, lot.shares))
        lots.remove(front)
        sold.append(front)
        left -= front.shares
    return sold


def _shift(lots: list[Lot], losses: list[list[int]], targets: list[Lot], limit: int) -> tuple[int, int]:
    """Moves up to limit [shares, loss] losses onto the target lots in order: (shares moved, cents moved)."""
    moved = cents = 0
    for lot in targets:
        while lot.shares and losses and moved < limit:
            count, loss = losses[0]
            front = _front(lots, lot, min(lot.shares, count, limit - moved))
            front.basis += loss
            front.absorbed = True
            moved += front.shares
            cents += front.shares * loss
            losses[0][0] -= front.shares
            if not losses[0][0]:
                losses.pop(0)
    return moved, cents


def _replay(trades: list[Trade], settle) -> tuple[list[SaleResult], list[SoldLot]]:
    """Sales in day order; settle(sale, lots, losses) returns the cents that sale has disallowed."""
    lots = [Lot(t.id, t.ticker, t.day, t.shares, t.price_cents) for t in trades if t.side is Side.BUY]
    results, ledger = [], []
    for sale in (t for t in trades if t.side is Side.SELL):
        sold = _sell(lots, sale)
        ledger += [SoldLot(sale.id, lot.buy_id, lot.shares, lot.basis, sale.price_cents - lot.basis) for lot in sold]
        losses = [[lot.shares, lot.basis - sale.price_cents] for lot in sold if lot.basis > sale.price_cents]
        disallowed = settle(sale, lots, losses)
        gain = sum(lot.shares * (sale.price_cents - lot.basis) for lot in sold)
        results.append(SaleResult(sale.id, gain + disallowed, disallowed))
    return results, ledger


def audit(trades: list[Trade], window: int = WINDOW, same_ticker: bool = True) -> list[SaleResult]:
    """The rules, at lot level. window and same_ticker exist to measure the mistakes a case must catch."""

    def settle(sale: Trade, lots: list[Lot], losses: list[list[int]]) -> int:
        targets = [
            lot
            for lot in lots
            if not lot.absorbed and abs(lot.day - sale.day) <= window and (lot.ticker == sale.ticker or not same_ticker)
        ]
        return _shift(lots, losses, targets, sale.shares)[1]

    return _replay(trades, settle)[0]


def apply(trades: list[Trade], matches: list[Match]) -> tuple[list[SaleResult], list[SoldLot]]:
    """Carries out the given matches, checking only that the shares exist: judging them is the agent's job."""
    sides = {trade.id: trade.side for trade in trades}
    for match in matches:
        if sides.get(match.sale_id) is not Side.SELL or sides.get(match.buy_id) is not Side.BUY:
            raise ValueError(f"no such sale and buy: {match.sale_id}, {match.buy_id}")

    def settle(sale: Trade, lots: list[Lot], losses: list[list[int]]) -> int:
        total = 0
        for match in (m for m in matches if m.sale_id == sale.id):
            targets = [lot for lot in lots if lot.buy_id == match.buy_id and not lot.absorbed]
            moved, cents = _shift(lots, losses, targets, match.shares)
            if moved != match.shares:
                raise ValueError(f"{match.sale_id} to {match.buy_id}: only {moved} of {match.shares} shares can move")
            total += cents
        return total

    return _replay(trades, settle)

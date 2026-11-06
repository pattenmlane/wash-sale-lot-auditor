"""Builds a year of trades from its seed; the answer comes from the lot-level ledger, the verifier's from units."""

from __future__ import annotations

from pathlib import Path

from contract import (
    ApplyMatchesInput,
    ApplyMatchesOutput,
    AuditInput,
    PinnedAuditOutput,
    SaleResult,
    Side,
    Trade,
    TradesOutput,
)
from plugin.ledger import apply, audit
from plugin.rng import Rng
from verifier.rules import MAX_SEED, WINDOW

TICKERS = ("ACME", "BOLT", "CRUX", "DUNE", "ECHO", "FERN")
ATTEMPTS = 500


def total(sales: list[SaleResult]) -> int:
    return sum(sale.realized_cents for sale in sales)


def _lot(rng: Rng, low: int = 4, high: int = 12) -> int:
    return 5 * rng.between(low, high)


def _price(rng: Rng) -> int:
    return 5 * rng.between(800, 1600)


def _drop(rng: Rng) -> int:
    return 5 * rng.between(20, 200)


def _plan(rng: Rng) -> list[tuple[int, str, Side, int, int]]:
    """A loss sale with a buy exactly 30 days off, and another with one exactly 31 off and the first's buy nearby."""
    main, other = rng.shuffled(TICKERS)[:2]
    start = rng.between(5, 90)
    first_sale = start + rng.between(10, 70)
    held = _lot(rng)
    sold = 5 * rng.between(2, held // 5)
    cost = _price(rng)
    bought = first_sale + rng.pick((WINDOW, -WINDOW))
    extra = _lot(rng, 2, 8)
    second_sale = max(first_sale, bought) + rng.between(5, 60)
    plan = [
        (start, main, Side.BUY, held, cost),
        (first_sale, main, Side.SELL, sold, cost - _drop(rng)),
        (bought, main, Side.BUY, extra, cost - _drop(rng)),
        (second_sale, main, Side.SELL, 5 * rng.between(1, (held + extra - sold) // 5), cost - _drop(rng) + _drop(rng)),
    ]

    # The other ticker's loss sale sits within reach of the main ticker's buy, which must not count.
    trap_sale = bought + rng.pick((-1, 1)) * rng.between(1, WINDOW)
    trap_cost = _price(rng)
    trap_held = _lot(rng)
    plan += [
        (trap_sale - rng.between(WINDOW + 2, 90), other, Side.BUY, trap_held, trap_cost),
        (trap_sale, other, Side.SELL, 5 * rng.between(2, trap_held // 5), trap_cost - _drop(rng)),
        (trap_sale + rng.pick((-1, 1)) * (WINDOW + 1), other, Side.BUY, _lot(rng, 2, 8), trap_cost - _drop(rng)),
    ]
    if rng.below(2):
        plan.append((second_sale + rng.between(WINDOW + 2, 90), main, Side.BUY, _lot(rng, 2, 8), _price(rng)))
    return plan


def _attempt(seed: int, attempt: int) -> PinnedAuditOutput | None:
    plan = sorted(_plan(Rng(f"trades:{seed}:{attempt}")), key=lambda row: row[0])
    days = [row[0] for row in plan]
    if len(set(days)) < len(days) or days[0] < 1 or days[-1] > 365:
        return None
    trades = [Trade(f"T{index}", *row) for index, row in enumerate(plan, 1)]
    try:
        sales = audit(trades)
    except ValueError:  # this plan went short
        return None
    # Every case needs a wash sale that only the 30th day catches, one the 31st day would wrongly add, a buy of
    # the other ticker that would wrongly count, and some deferred loss still unsold, so ignoring it all fails.
    misses = (audit(trades, WINDOW - 1), audit(trades, WINDOW + 1), audit(trades, same_ticker=False))
    if any(sales == miss for miss in misses) or total(sales) == total(audit(trades, -1)):
        return None
    return PinnedAuditOutput(seed, trades, sales, total(sales))


def build_case(seed: int) -> PinnedAuditOutput:
    if not 1 <= seed <= MAX_SEED:
        raise ValueError(f"seed must be 1 to {MAX_SEED}, got {seed}")
    for attempt in range(ATTEMPTS):
        case = _attempt(seed, attempt)
        if case is not None:
            return case
    raise RuntimeError(f"no usable trades for seed {seed} in {ATTEMPTS} attempts")


def pin_audit(given: AuditInput, workspace: Path) -> PinnedAuditOutput:
    return build_case(given.seed)


def read_trades(given: AuditInput, workspace: Path) -> TradesOutput:
    return TradesOutput(given.seed, build_case(given.seed).trades)


def apply_matches(given: ApplyMatchesInput, workspace: Path) -> ApplyMatchesOutput:
    sales, sold = apply(build_case(given.seed).trades, given.matches)
    return ApplyMatchesOutput(given.seed, sold, sales, total(sales))

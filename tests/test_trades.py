from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from slimconfig import plain_output

from contract import ApplyMatchesInput, AuditInput, Match, PinnedAuditOutput, Side
from plugin import apply_matches, read_trades
from plugin.ledger import apply, audit
from plugin.trades import build_case, total
from verifier.rules import WINDOW, replay_shares
from verifier.task import as_audit, key_problem


def decide(case: PinnedAuditOutput) -> list[Match]:
    """What a careful agent passes to apply_matches: only the stated rules and the tool's own output."""
    matches: list[Match] = []
    buys = [trade for trade in case.trades if trade.side is Side.BUY]
    sold = {buy.id: 0 for buy in buys}
    absorbed = {buy.id: 0 for buy in buys}  # the highest share number that has absorbed a loss
    for sale in (trade for trade in case.trades if trade.side is Side.SELL):
        lots = [lot for lot in apply(case.trades, matches)[1] if lot.sale_id == sale.id]
        for lot in lots:
            sold[lot.buy_id] += lot.shares
        losses = sum(lot.shares for lot in lots if lot.gain_cents < 0)
        for buy in buys:
            first = max(sold[buy.id], absorbed[buy.id])
            free = min(losses, buy.shares - first)
            if free > 0 and buy.ticker == sale.ticker and abs(buy.day - sale.day) <= WINDOW:
                matches.append(Match(sale.id, buy.id, free))
                absorbed[buy.id] = first + free
                losses -= free
    return matches


@pytest.mark.parametrize("seed", range(1, 301))
def test_every_case_is_confirmed_and_catches_each_mistake(seed: int) -> None:
    case = build_case(seed)
    assert key_problem(seed, case) is None
    right = as_audit(case.sales)
    assert sum(row[1] for row in right.values()) > 0  # at least one wash sale

    ignored = replay_shares(case.trades, -1)  # the naive strategy, by the verifier's replay
    assert sum(row[0] for row in ignored.values()) != case.total_realized_cents
    assert replay_shares(case.trades, WINDOW - 1) != right  # day 30 matters
    assert replay_shares(case.trades, WINDOW + 1) != right  # day 31 matters
    assert as_audit(audit(case.trades, same_ticker=False)) != right  # the other ticker matters


@pytest.mark.parametrize("seed", range(1, 301))
def test_every_case_keeps_to_its_shape(seed: int) -> None:
    trades = build_case(seed).trades
    days = [trade.day for trade in trades]
    assert 6 <= len(trades) <= 8 and len({trade.ticker for trade in trades}) == 2
    assert days == sorted(set(days)) and 1 <= days[0] and days[-1] <= 365
    assert all(trade.shares > 0 and trade.price_cents > 0 for trade in trades)


@pytest.mark.parametrize("seed", range(1, 301))
def test_the_rules_reach_the_answer_through_apply_matches(seed: int, tmp_path: Path) -> None:
    case = build_case(seed)
    made = apply_matches(ApplyMatchesInput(seed, decide(case)), tmp_path)
    assert made.sales == case.sales and made.total_realized_cents == case.total_realized_cents


def test_the_cases_exercise_every_rule() -> None:
    cases = [build_case(seed) for seed in range(1, 301)]
    partly = [case for case in cases if any(s.disallowed_cents and s.realized_cents < 0 for s in case.sales)]
    later = [case for case in cases if len([s for s in case.sales if s.disallowed_cents]) > 1]
    changed = [
        case
        for case in cases
        if any(
            not sale.disallowed_cents and sale.realized_cents != bare.realized_cents
            for sale, bare in zip(case.sales, audit(case.trades, -1))
        )
    ]
    assert partly and later and changed


def test_cases_are_reproducible_to_the_byte() -> None:
    digest = hashlib.sha256(json.dumps(plain_output(build_case(1)), sort_keys=True).encode()).hexdigest()
    assert digest == hashlib.sha256(json.dumps(plain_output(build_case(1)), sort_keys=True).encode()).hexdigest()
    assert digest == "7d6916b50961820bf3a0c060360da825c70a3e68b2cfca1154702f97d7688d5a"


def test_the_agent_never_sees_the_answer(tmp_path: Path) -> None:
    case = build_case(3)
    shown = plain_output(read_trades(AuditInput(3), tmp_path))
    assert set(shown) == {"seed", "trades"} and shown["trades"] == plain_output(case)["trades"]
    assert 'cents": -' not in json.dumps(shown) and "disallowed" not in json.dumps(shown)


def test_with_no_matches_the_tool_shows_only_plain_gains(tmp_path: Path) -> None:
    case = build_case(3)
    made = apply_matches(ApplyMatchesInput(3, []), tmp_path)
    assert all(sale.disallowed_cents == 0 for sale in made.sales)
    assert made.total_realized_cents == total(audit(case.trades, -1)) != case.total_realized_cents


@pytest.mark.parametrize("seed", [0, -1, 100_001])
def test_refuses_a_seed_out_of_range(seed: int) -> None:
    with pytest.raises(ValueError, match="seed"):
        build_case(seed)

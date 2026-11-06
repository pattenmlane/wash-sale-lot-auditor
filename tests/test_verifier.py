from __future__ import annotations

import json
from pathlib import Path

import pytest
from slimconfig import build_output, plain_output

import verifier
from contract import (
    ApplyMatchesInput,
    AuditInput,
    AuditOutput,
    Match,
    PinnedAuditOutput,
    SaleResult,
    SaveAuditInput,
    Side,
    Trade,
)
from plugin import pin_audit, save_audit
from plugin.ledger import apply, audit
from plugin.trades import total
from verifier.checks import repeated
from verifier.rules import replay_shares

SEED = 7
TASK = "audit-wash-sales"
BUY, SELL = Side.BUY, Side.SELL


# The verifier gets contract instances, as NanoAgent's sandbox builds them from JSON.
def key(tmp_path: Path) -> PinnedAuditOutput:
    return build_output(plain_output(pin_audit(AuditInput(SEED), tmp_path)), PinnedAuditOutput)


def judge(sales: list[SaleResult], tmp_path: Path, sum_of: int | None = None, reference=None) -> dict:
    made = save_audit(SaveAuditInput(SEED, sales, total(sales) if sum_of is None else sum_of), tmp_path)
    output = build_output(plain_output(made), AuditOutput)
    return verifier.verify_task(TASK, AuditInput(SEED), output, reference or key(tmp_path), str(tmp_path))


def submitted(pinned: PinnedAuditOutput) -> AuditOutput:
    return AuditOutput(SEED, f"audits/{SEED}.json", pinned.sales, pinned.total_realized_cents)


def test_accepts_the_right_audit(tmp_path: Path) -> None:
    verdict = judge(key(tmp_path).sales, tmp_path)
    assert verdict["valid"] is True and verdict["score"] == 1.0


def test_order_of_sales_does_not_matter(tmp_path: Path) -> None:
    assert judge(list(reversed(key(tmp_path).sales)), tmp_path)["valid"] is True


def test_refuses_ignoring_wash_sales(tmp_path: Path) -> None:
    verdict = judge(audit(key(tmp_path).trades, -1), tmp_path)
    assert verdict["valid"] is False and 0 <= verdict["score"] <= 0.99
    assert "sales" in verdict["details"]["failed"]


@pytest.mark.parametrize("window", [29, 31])
def test_refuses_the_boundary_mistakes(tmp_path: Path, window: int) -> None:
    verdict = judge(audit(key(tmp_path).trades, window), tmp_path)
    assert verdict["valid"] is False and verdict["score"] <= 0.99
    assert verdict["details"]["failed"][0] == "sales"


def test_refuses_counting_the_other_ticker(tmp_path: Path) -> None:
    verdict = judge(audit(key(tmp_path).trades, same_ticker=False), tmp_path)
    assert verdict["valid"] is False and verdict["details"]["failed"][0] == "sales"


def test_a_partly_right_audit_scores_below_one(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    first = pinned.sales[0]
    off = SaleResult(first.sale_id, first.realized_cents + 1, first.disallowed_cents)
    verdict = judge([off, *pinned.sales[1:]], tmp_path, pinned.total_realized_cents)
    assert verdict["details"]["failed"] == ["sales"]
    assert verdict["score"] == len(pinned.sales) / (len(pinned.sales) + 1)


def test_refuses_a_wrong_total_alone(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    verdict = judge(pinned.sales, tmp_path, pinned.total_realized_cents + 1)
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["total"] and verdict["score"] < 1


def test_refuses_a_submission_with_nothing_saved(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), submitted(pinned), pinned, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["saved"] and verdict["score"] == 0.0


def test_refuses_a_submission_that_differs_from_the_file(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    save_audit(SaveAuditInput(SEED, pinned.sales[:-1], pinned.total_realized_cents), tmp_path)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), submitted(pinned), pinned, str(tmp_path))
    assert verdict["valid"] is False and "differs" in verdict["message"]


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"seed": 7}',
        '{"seed": 7, "sales": 3, "total_realized_cents": 0}',
        '{"seed": 7, "sales": [1], "total_realized_cents": 0}',
        '{"seed": 7, "sales": [{"sale_id": "T1"}], "total_realized_cents": 0}',
    ],
)
def test_refuses_a_malformed_file(tmp_path: Path, text: str) -> None:
    pinned = key(tmp_path)
    (tmp_path / "audits").mkdir()
    (tmp_path / "audits" / f"{SEED}.json").write_text(text)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), submitted(pinned), pinned, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["saved"]


def test_refuses_another_path(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    save_audit(SaveAuditInput(SEED, pinned.sales, pinned.total_realized_cents), tmp_path)
    output = AuditOutput(SEED, "../elsewhere.json", pinned.sales, pinned.total_realized_cents)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), output, pinned, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["saved"]


def test_refuses_another_seed(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    made = save_audit(SaveAuditInput(8, pinned.sales, pinned.total_realized_cents), tmp_path)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), made, pinned, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["seed"]


def test_refuses_missing_unknown_and_repeated_sales(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    first = pinned.sales[0]
    buy = next(trade.id for trade in pinned.trades if trade.side is BUY)
    assert judge(pinned.sales[1:], tmp_path)["details"]["failed"] == ["coverage"]
    assert judge([first, *pinned.sales], tmp_path)["details"]["failed"] == ["coverage"]
    assert judge([*pinned.sales, SaleResult(buy, 0, 0)], tmp_path)["details"]["failed"] == ["coverage"]
    assert judge([*pinned.sales, SaleResult("T99", 0, 0)], tmp_path)["details"]["failed"] == ["coverage"]
    assert judge([], tmp_path)["details"]["failed"] == ["coverage"]


def test_refuses_a_missing_or_altered_answer_key(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    save_audit(SaveAuditInput(SEED, pinned.sales, pinned.total_realized_cents), tmp_path)
    output = submitted(pinned)
    assert verifier.verify_task(TASK, AuditInput(SEED), output, None, str(tmp_path))["score"] == 0.0
    first = pinned.sales[0]
    pinned.sales[0] = SaleResult(first.sale_id, first.realized_cents + 1, first.disallowed_cents)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), output, pinned, str(tmp_path))
    assert verdict["details"]["failed"] == ["answer-key"] and verdict["score"] == 0.0


def test_refuses_a_key_for_another_seed_or_with_a_short_sale(tmp_path: Path) -> None:
    pinned = key(tmp_path)
    assert verifier.verify_task(TASK, AuditInput(8), submitted(pinned), pinned, str(tmp_path))["score"] == 0.0
    short = PinnedAuditOutput(SEED, [Trade("T1", 5, "ACME", SELL, 5, 100)], [SaleResult("T1", 0, 0)], 0)
    verdict = judge(short.sales, tmp_path, reference=short)
    assert verdict["details"]["failed"] == ["answer-key"] and "nobody holds" in verdict["message"]


def both(trades: list[Trade]) -> dict:
    """The rules' answer: the ledger and the share-by-share replay must agree on it."""
    lines = {sale.sale_id: (sale.realized_cents, sale.disallowed_cents) for sale in audit(trades)}
    assert lines == replay_shares(trades)
    return lines


@pytest.mark.parametrize(
    ("gap", "washed"),
    [(-31, False), (-30, True), (-29, True), (29, True), (30, True), (31, False)],
)
def test_the_window_counts_day_30_but_not_31(gap: int, washed: bool) -> None:
    trades = [
        Trade("T1", 1, "ACME", BUY, 10, 1000),
        Trade("T2", 100 + gap, "ACME", BUY, 10, 900),
        Trade("T3", 100, "ACME", SELL, 10, 800),
    ]
    assert both(sorted(trades, key=lambda t: t.day))["T3"] == ((0, 2000) if washed else (-2000, 0))


def test_a_buy_of_the_other_ticker_is_no_replacement() -> None:
    trades = [
        Trade("T1", 1, "ACME", BUY, 10, 1000),
        Trade("T2", 100, "ACME", SELL, 10, 800),
        Trade("T3", 105, "BOLT", BUY, 10, 800),
    ]
    assert both(trades)["T2"] == (-2000, 0)


def test_the_earliest_buy_matches_first_and_later_gains_change() -> None:
    trades = [
        Trade("T1", 1, "ACME", BUY, 10, 1000),
        Trade("T2", 70, "ACME", BUY, 4, 900),
        Trade("T3", 80, "ACME", SELL, 10, 800),
        Trade("T4", 90, "ACME", BUY, 4, 900),
        Trade("T5", 200, "ACME", SELL, 6, 1100),
    ]
    # Eight shares absorb 200 each, and two losses stay allowed; T5 sells T2's four and two of T4's, all absorbed.
    assert both(trades) == {"T3": (-400, 1600), "T5": (0, 0)}


def test_the_rest_of_the_same_buy_counts_but_the_shares_sold_do_not() -> None:
    trades = [Trade("T1", 1, "ACME", BUY, 10, 1000), Trade("T2", 20, "ACME", SELL, 4, 700)]
    assert both(trades)["T2"] == (0, 1200)
    trades = [Trade("T1", 1, "ACME", BUY, 4, 1000), Trade("T2", 20, "ACME", SELL, 4, 700)]
    assert both(trades)["T2"] == (-1200, 0)


def test_a_share_absorbs_only_one_loss_but_can_pass_its_own_on() -> None:
    trades = [
        Trade("T1", 1, "ACME", BUY, 2, 1000),
        Trade("T2", 50, "ACME", SELL, 2, 900),
        Trade("T3", 60, "ACME", BUY, 2, 900),
        Trade("T4", 70, "ACME", SELL, 2, 850),
        Trade("T5", 80, "ACME", BUY, 1, 850),
    ]
    # T3's shares absorb 100 each and sell at a loss of 150; T5's one share takes one, the other stays allowed.
    assert both(trades) == {"T2": (0, 200), "T4": (-150, 150)}


def test_only_the_loss_shares_of_a_mixed_sale_count() -> None:
    trades = [
        Trade("T1", 1, "ACME", BUY, 2, 800),
        Trade("T2", 2, "ACME", BUY, 2, 1200),
        Trade("T3", 3, "ACME", BUY, 2, 1000),
        Trade("T4", 100, "ACME", SELL, 5, 1000),
        Trade("T5", 110, "ACME", BUY, 1, 1000),
    ]
    # Two gains of 200, two losses of 200, and a share sold at its basis, which has no loss to match.
    assert both(trades)["T4"] == (200, 200)


def test_apply_carries_out_matches_without_judging_them() -> None:
    trades = [
        Trade("T1", 1, "ACME", BUY, 10, 1000),
        Trade("T2", 100, "ACME", SELL, 10, 800),
        Trade("T3", 131, "ACME", BUY, 10, 800),
        Trade("T4", 200, "ACME", SELL, 10, 800),
    ]
    sales, sold = apply(trades, [Match("T2", "T3", 10)])  # 31 days off, so wrong, but carried out
    assert [sale.disallowed_cents for sale in sales] == [2000, 0]
    assert sold[1].basis_cents == 1000 and sold[1].gain_cents == -200


@pytest.mark.parametrize(
    "match",
    [Match("T2", "T3", 11), Match("T1", "T3", 1), Match("T2", "T9", 1), Match("T3", "T2", 1)],
)
def test_apply_refuses_shares_that_do_not_exist(match: Match) -> None:
    trades = [
        Trade("T1", 1, "ACME", BUY, 10, 1000),
        Trade("T2", 100, "ACME", SELL, 10, 800),
        Trade("T3", 120, "ACME", BUY, 20, 800),
    ]
    with pytest.raises(ValueError):
        apply(trades, [match])


def test_refuses_bad_tool_input() -> None:
    assert verifier.verify_input("read_trades", AuditInput(0))["valid"] is False
    assert verifier.verify_input("read_trades", AuditInput(100_001))["valid"] is False
    assert verifier.verify_input("read_trades", AuditInput(100_000))["valid"] is True
    twice = SaveAuditInput(1, [SaleResult("T1", 0, 0), SaleResult("T1", 1, 0)], 1)
    assert verifier.verify_input("save_audit", twice)["valid"] is False
    assert verifier.verify_input("apply_matches", ApplyMatchesInput(1, [Match("T1", "T2", 0)]))["valid"] is False


def test_the_saved_file_is_what_the_tool_reports(tmp_path: Path) -> None:
    given = SaveAuditInput(SEED, [SaleResult("T3", -5, 10)], -5)
    made = save_audit(given, tmp_path)
    assert made.path == f"audits/{SEED}.json"
    assert json.loads((tmp_path / made.path).read_text())["sales"] == [
        {"sale_id": "T3", "realized_cents": -5, "disallowed_cents": 10}
    ]
    assert verifier.verify_output("save_audit", given, made, str(tmp_path))["valid"] is True
    (tmp_path / made.path).unlink()
    assert verifier.verify_output("save_audit", given, made, str(tmp_path))["valid"] is False


def test_repeated_handles_enums() -> None:
    assert repeated([BUY, SELL, BUY, SELL]) == [BUY, SELL]


@pytest.mark.parametrize(
    "sales",
    [
        [SaleResult("", 0, 0)],
        [SaleResult("T1", -(10**30), 10**30)],
        [SaleResult("☃", -1, -1), SaleResult("☃", -1, -1)],
        [SaleResult("../../etc/passwd", 0, 0)],
    ],
)
def test_nonsense_of_the_right_type_is_refused_not_raised(tmp_path: Path, sales: list[SaleResult]) -> None:
    verdict = judge(sales, tmp_path, -(10**30))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["coverage"]


def test_nonsense_lines_for_the_real_sales_are_refused_not_raised(tmp_path: Path) -> None:
    sales = [SaleResult(sale.sale_id, -(10**30), -1) for sale in key(tmp_path).sales]
    verdict = judge(sales, tmp_path, 10**30)
    assert verdict["valid"] is False and verdict["score"] == 0.0 and verdict["details"]["failed"] == ["sales", "total"]


@pytest.mark.parametrize("path", ["", "\0", "audits", "/etc/passwd", "audits/7.json\0"])
def test_a_nonsense_path_is_refused_not_raised(tmp_path: Path, path: str) -> None:
    pinned = key(tmp_path)
    output = AuditOutput(SEED, path, pinned.sales, pinned.total_realized_cents)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), output, pinned, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["saved"]
    given = SaveAuditInput(SEED, pinned.sales, pinned.total_realized_cents)
    assert verifier.verify_output("save_audit", given, output, str(tmp_path))["valid"] is False


@pytest.mark.parametrize("data", [b"\xff\xfe\x00", b"[" * 200_000, b'{"seed": ' + b"9" * 5000 + b"}"])
def test_a_file_that_cannot_be_parsed_is_refused_not_raised(tmp_path: Path, data: bytes) -> None:
    pinned = key(tmp_path)
    (tmp_path / "audits").mkdir()
    (tmp_path / "audits" / f"{SEED}.json").write_bytes(data)
    verdict = verifier.verify_task(TASK, AuditInput(SEED), submitted(pinned), pinned, str(tmp_path))
    assert verdict["valid"] is False and verdict["details"]["failed"] == ["saved"]

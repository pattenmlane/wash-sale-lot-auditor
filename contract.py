"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    PIN_AUDIT = "pin_audit"
    READ_TRADES = "read_trades"
    APPLY_MATCHES = "apply_matches"
    SAVE_AUDIT = "save_audit"


class Task(Enum):
    AUDIT_WASH_SALES = "audit-wash-sales"


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


SEED = "The case number, 1 to 100000: the same number always gives the same trades"
TRADES = "Every trade of the year, by day; no two trades share a day"
SALES = "One line per sale"
TOTAL = "The sum of every sale's realized_cents"


@dataclass
class Trade(Output):
    id: Annotated[str, "The trade's id"]
    day: Annotated[int, "The day of the year, 1 to 365"]
    ticker: Annotated[str, "The stock traded"]
    side: Annotated[Side, "Whether shares were bought or sold"]
    shares: Annotated[int, "How many whole shares"]
    price_cents: Annotated[int, "The price of one share, in cents"]


@dataclass
class Match(Output):
    sale_id: Annotated[str, "The sale whose next loss shares are disallowed"]
    buy_id: Annotated[str, "The buy whose next free shares absorb those losses"]
    shares: Annotated[int, "How many shares, one loss to one replacement share"]


@dataclass
class SaleResult(Output):
    sale_id: Annotated[str, "The sale's trade id"]
    realized_cents: Annotated[int, "The gain after disallowance, in cents; negative for a loss"]
    disallowed_cents: Annotated[int, "The loss disallowed as a wash sale, in cents; 0 if none"]


@dataclass
class SoldLot(Output):
    sale_id: Annotated[str, "The sale"]
    buy_id: Annotated[str, "The buy these shares came from"]
    shares: Annotated[int, "How many shares of that buy, all with the same basis"]
    basis_cents: Annotated[int, "The basis of each share when sold, absorbed losses included"]
    gain_cents: Annotated[int, "Sale price minus basis for each share; negative for a loss share"]


@dataclass
class AuditInput(Output):
    seed: Annotated[int, SEED]


@dataclass
class TradesOutput(Output):
    seed: Annotated[int, SEED]
    trades: Annotated[list[Trade], TRADES]


@dataclass
class PinnedAuditOutput(Output):
    # The answer key: the trades and the lot-level audit, out of the agent's sight.
    seed: Annotated[int, SEED]
    trades: Annotated[list[Trade], TRADES]
    sales: Annotated[list[SaleResult], SALES]
    total_realized_cents: Annotated[int, TOTAL]


@dataclass
class ApplyMatchesInput(Output):
    seed: Annotated[int, SEED]
    matches: Annotated[list[Match], "The wash sale matches you decided on; empty for none"]


@dataclass
class ApplyMatchesOutput(Output):
    seed: Annotated[int, SEED]
    sold: Annotated[list[SoldLot], "What each sale sold, under these matches"]
    sales: Annotated[list[SaleResult], SALES]
    total_realized_cents: Annotated[int, TOTAL]


@dataclass
class SaveAuditInput(Output):
    seed: Annotated[int, SEED]
    sales: Annotated[list[SaleResult], SALES]
    total_realized_cents: Annotated[int, TOTAL]


@dataclass
class AuditOutput(Output):
    seed: Annotated[int, SEED]
    path: Annotated[str, "The saved audit, relative to the plugin workspace"]
    sales: Annotated[list[SaleResult], SALES]
    total_realized_cents: Annotated[int, TOTAL]


TOOLS = {
    Tool.PIN_AUDIT: (AuditInput, PinnedAuditOutput),
    Tool.READ_TRADES: (AuditInput, TradesOutput),
    Tool.APPLY_MATCHES: (ApplyMatchesInput, ApplyMatchesOutput),
    Tool.SAVE_AUDIT: (SaveAuditInput, AuditOutput),
}
TASKS = {Task.AUDIT_WASH_SALES: (AuditInput, AuditOutput)}

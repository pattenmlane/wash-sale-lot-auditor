"""The wash sale rules, replayed one share at a time: every share is its own record, no lots anywhere."""

from contract import Side

MAX_SEED = 100_000
WINDOW = 30


def replaces(share, sale, window):
    """Whether a share can absorb this sale's next loss."""
    near = abs(share["day"] - sale.day) <= window
    return share["ticker"] == sale.ticker and near and not share["sold"] and not share["absorbed"]


def replay_shares(trades, window=WINDOW):
    """{sale id: (realized cents, disallowed cents)}, or None when a sale sells shares nobody holds."""
    by_day = sorted(trades, key=lambda trade: trade.day)
    shares = [
        {"ticker": t.ticker, "day": t.day, "basis": t.price_cents, "sold": False, "absorbed": False}
        for t in by_day
        if t.side is Side.BUY
        for _ in range(t.shares)
    ]
    audit = {}
    for sale in (t for t in by_day if t.side is Side.SELL):
        held = [s for s in shares if s["ticker"] == sale.ticker and s["day"] < sale.day and not s["sold"]]
        if len(held) < sale.shares:
            return None
        sold = held[: sale.shares]
        for share in sold:
            share["sold"] = True
        realized = disallowed = 0
        for share in sold:
            gain = sale.price_cents - share["basis"]
            twin = next((s for s in shares if replaces(s, sale, window)), None) if gain < 0 else None
            if twin is None:
                realized += gain
            else:
                twin["basis"] -= gain
                twin["absorbed"] = True
                disallowed -= gain
        audit[sale.id] = (realized, disallowed)
    return audit

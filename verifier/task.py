"""The verdict on a submitted audit: named constraints, judged in order."""

from contract import Side

from .checks import repeated, result, saved_json
from .rules import replay_shares


def as_audit(sales):
    return {sale.sale_id: (sale.realized_cents, sale.disallowed_cents) for sale in sales}


def key_problem(seed, pinned):
    """Why the answer key can't be trusted, or None. The share-by-share replay must reach the ledger's answer."""
    if pinned is None:
        return "no answer key was pinned"
    if pinned.seed != seed:
        return f"the answer key is for seed {pinned.seed}, not {seed}"
    audit = replay_shares(pinned.trades)
    if audit is None:
        return "a sale sells shares nobody holds"
    same = audit == as_audit(pinned.sales) and sum(row[0] for row in audit.values()) == pinned.total_realized_cents
    return None if same else "the share-by-share replay does not confirm the answer key"


def saved_problem(output, workspace):
    expected = f"audits/{output.seed}.json"
    if output.path != expected:
        return f"the submission names {output.path!r}, not {expected!r}"
    saved = saved_json(workspace, expected)
    if saved is None:
        return f"no audit is saved at {expected}: call save_audit before submitting"
    try:
        lines = [(s["sale_id"], s["realized_cents"], s["disallowed_cents"]) for s in saved["sales"]]
        same = saved["seed"] == output.seed and saved["total_realized_cents"] == output.total_realized_cents
    except (KeyError, TypeError):
        return f"the file at {expected} is not an audit"
    submitted = [(s.sale_id, s.realized_cents, s.disallowed_cents) for s in output.sales]
    return None if same and lines == submitted else f"the submission differs from the audit saved at {expected}"


def coverage_problem(output, pinned):
    """One line per sale, and only sales."""
    named = [sale.sale_id for sale in output.sales]
    known = {trade.id for trade in pinned.trades if trade.side is Side.SELL}
    if repeated(named):
        return f"listed more than once: {', '.join(repeated(named))}"
    if known - set(named):
        return f"never listed: {', '.join(sorted(known - set(named)))}"
    return f"not a sale: {', '.join(sorted(set(named) - known))}" if set(named) - known else None


def audit_verdict(arguments, output, reference, workspace):
    problem = key_problem(arguments.seed, reference)
    if problem:
        return result(False, f"answer-key: {problem}", score=0.0, failed=["answer-key"])
    if output.seed != arguments.seed:
        return result(False, f"seed: the submission is for seed {output.seed}", score=0.0, failed=["seed"])
    problem = saved_problem(output, workspace)
    if problem:
        return result(False, f"saved: {problem}", score=0.0, failed=["saved"])
    problem = coverage_problem(output, reference)
    if problem:
        return result(False, f"coverage: {problem}", score=0.0, failed=["coverage"])

    mine, best = as_audit(output.sales), as_audit(reference.sales)
    wrong = sorted(sale for sale in best if mine[sale] != best[sale])
    total_right = output.total_realized_cents == reference.total_realized_cents
    if not wrong and total_right:
        return result(True, f"All checks hold: every sale and the total of {reference.total_realized_cents} are right")
    failed = (["sales"] if wrong else []) + ([] if total_right else ["total"])
    first = f"sales: wrong for {', '.join(wrong)}" if wrong else f"total: not {output.total_realized_cents}"
    score = min((len(best) - len(wrong) + total_right) / (len(best) + 1), 0.99)
    return result(False, first, score=score, failed=failed, expected=best, total=reference.total_realized_cents)

"""The deterministic verifier: a share-by-share replay of the rules, on contract instances. No model."""

from contract import Task, Tool

from .checks import repeated, result, saved_json
from .rules import MAX_SEED
from .task import audit_verdict, key_problem

TASKS = {Task.AUDIT_WASH_SALES: audit_verdict}


def verify_input(tool, value):
    if not 1 <= value.seed <= MAX_SEED:
        return result(False, f"seed must be 1 to {MAX_SEED}")
    match Tool(tool):
        case Tool.SAVE_AUDIT:
            twice = repeated([sale.sale_id for sale in value.sales])
            if twice:
                return result(False, f"listed more than once: {', '.join(twice)}")
        case Tool.APPLY_MATCHES:
            if any(match.shares < 1 for match in value.matches):
                return result(False, "every match moves at least one share")
    return result(True, "input is valid")


def verify_output(tool, input_value, output_value, workspace):
    if output_value.seed != input_value.seed:
        return result(False, "the output is for another seed")
    match Tool(tool):
        case Tool.PIN_AUDIT:
            problem = key_problem(input_value.seed, output_value)
            return result(not problem, problem or "the answer key holds")
        case Tool.READ_TRADES:
            return result(bool(output_value.trades), "the case has trades")
        case Tool.APPLY_MATCHES:
            return result(bool(output_value.sales), "every sale is priced")
        case Tool.SAVE_AUDIT:
            saved = saved_json(workspace, output_value.path)
            return result(saved is not None, "saved" if saved is not None else "nothing was saved")


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)

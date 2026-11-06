from __future__ import annotations

import json
from pathlib import Path

from slimconfig import plain_output

from contract import AuditOutput, SaveAuditInput


def save_audit(given: SaveAuditInput, workspace: Path) -> AuditOutput:
    relative = f"audits/{given.seed}.json"
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plain_output(given), indent=2), encoding="utf-8")
    return AuditOutput(given.seed, relative, given.sales, given.total_realized_cents)

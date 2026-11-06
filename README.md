# Wash Sale Lot Auditor

A `nanoagent.plugin/v0001` plugin. Its task gives an agent a seeded year of stock
trades and asks for each sale's realized gain and disallowed loss under exact wash
sale rules. Everything runs offline: a case is built from its seed alone.

## Tools

| Tool | Does | Code |
|---|---|---|
| `pin_audit` | The answer key: the trades and the lot-level audit, hidden from the agent | `src/plugin/trades.py` |
| `read_trades` | Every buy and sell of the case, without the answer | `src/plugin/trades.py` |
| `apply_matches` | Carries out the agent's matches and does the arithmetic, without judging them | `src/plugin/trades.py`, `src/plugin/ledger.py` |
| `save_audit` | Saves the sale lines and total to `audits/<seed>.json` | `src/plugin/audit_file.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `audit-wash-sales` | Finds the wash sales and saves the audit | `agent`, with `read_trades`, `apply_matches` and `save_audit`; reference `pin_audit` |

## Verification

The generator's answer comes from a lot-level ledger that splits lots only where
a sale or a match cuts them. The verifier needs no stored answer: it makes one
record per share, replays the year share by share, and refuses a key that
disagrees. It then reads the saved file, not just the submission, and judges in
order: `answer-key`, `seed`, `saved`, `coverage`, `sales`, `total`. Integrity
failures score 0. Otherwise the score is the share of sale lines and total that
are right, at most 0.99 unless all are.

Every case holds a wash sale that only day 30 catches, a loss sale with a buy
exactly 31 days off, and a loss sale with the other ticker's buy in its window,
each of which changes the answer if misread. Ignoring wash sales gives the wrong
total on every case, because some deferred loss is still unsold at year end.

## Limitations

- These are the task's own rules, not tax advice. In particular, the unsold shares
  of the same buy count as replacements, and only shares still held can absorb a loss.
- `apply_matches` does the arithmetic, so the agent is judged on its matches and
  on working out what they do to later sales, not on multiplying.
- An audit saved by an earlier run with the same seed still counts if the agent
  submits it without saving again. The answer is right either way.
- Cases are small, 7 or 8 trades, to fit the hosted agent's step and token limits.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # environment variable NAMEs this plugin needs, never values
├── src/plugin/      # the MCP server, the seeded generator, the lot-level ledger and the audit writer
├── tests/
├── ui/              # how the page draws the outputs: renderers.js and renderers.css
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package
```

`contract.py` is the one place a value's shape is declared. Its `Output`
classes are the JSON Schemas the server offers and the agent sees, and every
input and output is built into its class on the way in and out: the server,
NanoAgent and the verifier all get typed values, never loose dicts. A tool
that fails raises; NanoAgent sees an MCP error.

To add a tool: add a `Tool` member, its input and output classes and its
`TOOLS` entry to `contract.py` (a snake_case name, classes named `...Input`
and `...Output`); write its implementation in `src/plugin/`, taking its input
and the workspace and returning its output; write its `verify_input` /
`verify_output` in `verifier/`, and tests for both. Then register it in
`src/plugin/__main__.py` (`IMPLEMENTATIONS`), `verifier/__init__.py` (`TOOLS`),
`nanoagent.yaml` (`tools`) and this README's Tools table; a task goes in its
Tasks table.

`LICENSE` stays the template's MIT license under your name, `.gitignore`
keeps its entries, and this README keeps its title and sections: NanoAgent refuses a plugin
that changes them (rule 10 of `nanoagent.plugin.manifest`). Renaming the
plugin means renaming it in `nanoagent.yaml` and this title together.

To add a task, add a `Task` member (a kebab-case id) and its `TASKS` input and
output classes to `contract.py`, and declare it in `nanoagent.yaml` with its `runner` (`tool`,
`agent` or `decide`) and a `reference` tool, or `null` if it has none. A `tool`
task's classes are its tool's; an `agent` task's agent ends by calling `submit`
with the task's output; a `decide` task's model only chooses, and every tool
argument and output field is an Enum or bool, or copied from a value of exactly
its type in the task's input or an earlier tool output. Then add the check of
its output, `verify_task(arguments, output, reference, workspace)`, to `TASKS`
in `verifier/__init__.py`. People use the plugin by chatting with its agent,
which runs its tasks and shows each output on the page (see `ui/`).

## Develop and run

```bash
uv sync --extra dev
uv run pytest
```

Publishing checks every plugin rule: push the plugin to a public GitHub
repository and run `rush publish <server> <github-url>`.

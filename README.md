<<<<<<< HEAD
# garuda-harness
=======
# Garuda Harness

A provider-neutral execution and continuity layer for Garuda.

> The harness owns execution state; Garuda owns verified system state.

## Current status

H1 — read-only MCP controller.

The first release will:

- Start `garuda-mcp` over stdio.
- Discover MCP tools dynamically.
- Allow only read-only tools.
- Enforce call, timeout, result-size, and repeated-call budgets.
- Record redacted JSONL events.
- Write a run manifest.
- Replay recorded runs without MCP.

The first release will not:

- Modify source files.
- Apply patches.
- Execute agent-generated commands.
- Call mutating Garuda tools.
- Persist policy evaluations.
- Perform autonomous remediation.
- Merge code.
- Provide provider adapters.
- Provide sandbox execution.

## Repository relationship

```text
Garuda core       → semantic state, evidence, policies, governance, MCP
Garuda Harness    → bounded execution state, events, budgets, replay
Agent             → proposes observations and actions
```

Garuda remains the authority for verified system state. The harness must not become a second semantic graph or policy store.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

pytest
ruff check .
mypy harness
```

## Local Garuda dependency

Build the MCP server in the Garuda repository:

```bash
cd ~/garuda
go build -o ./bin/garuda-mcp ./cmd/garuda-mcp
```

Run the existing protocol verifier:

```bash
cd ~/garuda
WORKSPACE=go-validation-10 python3 scripts/mcp_verify.py
```

The current reference verifier reports 38/38 checks.

## H1 safety boundary

The harness is read-only by default. It must reject:

```text
garuda.propose_decision
garuda.handoff
garuda.resume
```

It must also reject arbitrary subprocess execution and filesystem mutation until a later phase explicitly introduces a Tool Broker and sandbox contract.
>>>>>>> 0e13255 (chore: add Garuda Harness repository foundation)

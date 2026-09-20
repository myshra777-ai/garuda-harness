# Garuda Harness architecture

## Authority split

Garuda owns verified system state:

- Semantic graph.
- Documentation claims.
- Runtime evidence.
- Policies and outcomes.
- Decisions and Merkle records.
- Existing task and checkpoint coordination.

The harness owns execution state:

- Runs.
- Attempts.
- Actions.
- Artifacts.
- Budgets.
- Replay journal.
- Controller recovery.
- Future worktree and sandbox lifecycle.

Agent reasoning is not automatically evidence.

## H1 flow

```text
Start garuda-mcp
        ↓
initialize
        ↓
notifications/initialized
        ↓
tools/list
        ↓
read-only tool allowlist
        ↓
bounded tool calls
        ↓
redacted JSONL event journal
        ↓
run manifest
        ↓
offline replay
```

## H1 does not mutate

H1 must not:

- Write source files.
- Apply patches.
- Run arbitrary commands.
- Call mutating MCP tools.
- Persist decisions.
- Perform handoffs.
- Merge code.

## Future phases

- H2: context projection and Context Manifest.
- H3: worktrees and Tool Broker.
- H4: bounded single-agent execution.
- H5: sandbox provider.
- H6: portable handoff.
- H7: recovery and leases.
- H8: minimal-change governance.
- H9: independent review.
- H10: multi-agent execution.

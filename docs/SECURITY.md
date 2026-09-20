# Harness security boundary

## H1 threat model

H1 starts a configured MCP server and invokes read-only tools. It does not execute model-generated shell commands or modify repositories.

## Fail-closed rules

The controller must reject:

- Unknown tools.
- Mutating Garuda tools.
- Missing or invalid tool schemas.
- Exceeded call budgets.
- Exceeded wall-clock budgets.
- Oversized results.
- Repeated identical calls beyond the retry budget.
- Invalid JSON-RPC responses.
- Non-clean process termination.

## Privacy

The event journal must not record raw free-form queries, checkpoint payloads, agent reasoning, credentials, or arbitrary MCP arguments. Record only safe allowlisted fields, digests, status, timing, and bounded metadata.

## Future sandboxing

H1 is not a sandbox. A future execution phase must add filesystem, process, network, resource, and credential isolation separately from Garuda policy evaluation.

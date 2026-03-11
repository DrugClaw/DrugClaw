# MCP Rust SDK Migration Evaluation

Date: 2026-02-11

## Current State

DrugClaw currently implements MCP client logic directly in `src/mcp.rs` and supports:
- `stdio` transport
- `streamable_http` transport (JSON-RPC over HTTP endpoint)
- Protocol negotiation at initialize time (default `2024-11-05`, configurable)

## Why evaluate official Rust MCP SDK

Potential benefits from migrating to the official Rust SDK:
- Better long-term protocol compatibility as MCP evolves.
- Shared transport abstractions and less custom maintenance.
- Consistent behavior with ecosystem tooling and examples.

Potential costs/risks:
- Refactor effort in an already working code path.
- Possible behavior drift in retry/error semantics and logging.
- New dependency surface and upgrade policy to maintain.

## Recommended approach

1. Keep current implementation as production path for now.
2. Add an adapter layer (`McpClient` trait) to decouple `ToolRegistry` from transport implementation.
3. Implement SDK-backed client behind an opt-in config flag.
4. Run A/B tests in CI against representative MCP servers:
   - stdio filesystem server
   - streamable HTTP server
5. Flip default only after parity on:
   - initialize/list/call behavior
   - timeout handling
   - error propagation format

## Exit criteria for migration

- Functional parity with existing MCP tests and production flows.
- No regression in tool discovery and invocation latency.
- Clear rollback path (config-level switch) retained for at least one release.

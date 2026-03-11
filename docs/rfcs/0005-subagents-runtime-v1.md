# RFC 0005: Session-Native Subagents Runtime (V1)

- Status: In Progress
- Owner: runtime/storage
- Created: 2026-03-09
- Related: #205

## Context

DrugClaw had a `sub_agent` tool that embedded a mini agent loop inside one tool call. It worked for quick delegation but lacked lifecycle controls, observability, and robust orchestration semantics.

OpenClaw and Spacebot both show stronger patterns:
- session-native spawn primitives
- explicit run lifecycle and cancellation
- non-blocking dispatch + eventual completion signal

## Goals

1. Replace tool-embedded delegation with session-native asynchronous subagent runs.
2. Keep parent chat responsive while subagent runs in background.
3. Provide practical controls: spawn/list/info/kill.
4. Persist run state for reliability and post-mortem diagnostics.
5. Keep security conservative: restricted child tool registry and chat permission checks.

## Non-Goals (V1)

1. Thread-bound session routing.
2. Nested orchestrator trees (depth > 1).
3. Guaranteed exactly-once announce delivery across process restart.
4. Per-run model override policy matrix.

## Proposed Design

### Tool Surface

- `sessions_spawn(task, context?, chat_id?)`
- `subagents_list(chat_id?, limit?)`
- `subagents_info(run_id, chat_id?)`
- `subagents_kill(run_id|"all", chat_id?)`
- `subagents_log(run_id, chat_id?, limit?)`
- `subagents_focus(run_id, chat_id?)`
- `subagents_unfocus(chat_id?)`
- `subagents_focused(chat_id?)`
- `subagents_send(message, chat_id?)`
- `subagents_retry_announces(batch?)`

### Runtime

- Dedicated in-process lane using semaphore (`subagents.max_concurrent`).
- Each spawn creates a `run_id` and returns immediately (`status=accepted`).
- Worker transition states: `accepted -> queued -> running -> completed|failed|timed_out|cancelled`.
- Cancellation is cooperative:
  - `subagents_kill` sets `cancel_requested=1`
  - runtime checks cancellation between model/tool iterations.

### Storage

`subagent_runs` table stores:
- identity: `run_id`, `chat_id`, `caller_channel`
- input: `task`, `context`
- lifecycle: `status`, `created_at`, `started_at`, `finished_at`, `cancel_requested`
- outputs: `result_text`, `error_text`
- cost: `input_tokens`, `output_tokens`, `total_tokens`, `provider`, `model`

### Child Execution

- Child uses restricted registry (`ToolRegistry::new_sub_agent`).
- No recursive subagent spawn in child registry.
- Timeout (`subagents.run_timeout_secs`) enforced with `tokio::time::timeout`.

### Completion Announce

- Optional chat announce (`subagents.announce_to_chat`, default true).
- On completion, runtime sends summary message back to parent chat with status and token usage.
- Delivery is best effort in V1.

## Config

```yaml
subagents:
  max_concurrent: 4
  max_active_per_chat: 5
  run_timeout_secs: 900
  announce_to_chat: true
```

## Why This Is Practical

1. No architectural rewrite of channel adapters.
2. Reuses existing tool execution and permission model.
3. Adds immediate user value (background work + cancellation) with bounded complexity.
4. Leaves room for V2 upgrades (nested orchestration and thread-binding) without breaking API.

## Comparison and Beyond

### Compared to OpenClaw docs baseline

- Matches core lifecycle controls (`spawn/list/info/kill`) and non-blocking spawn semantics.
- Adds direct DB-backed run records in DrugClaw runtime for simpler local introspection.

### Compared to Spacebot patterns

- Adopts asynchronous worker style and isolated task execution.
- Prioritizes minimal deploy risk over full multi-process decomposition in V1.

### How We Intend to Surpass (V2)

1. Add structured run events and latency histograms per phase.
2. Add depth-limited orchestrator mode (`max_spawn_depth=2`) for fan-out/fan-in.
3. Add adapter-specific thread binding with auto-focus lifecycle.
4. Add retryable announce queue persisted to DB for restart resilience.

## Delivery Plan (5 incremental commits in one PR)

1. Nested orchestration constraints: `max_spawn_depth`, `max_children_per_run`, parent-child run linkage.
2. Reliable announce path: persisted announce queue + retry + manual flush tool.
3. Observability: run event timeline and `subagents_log`.
4. Practical binding: focus/unfocus/focused/send workflow for chat-level subagent continuity.
5. Docs/regression/update generated artifacts and planning records.

## Testing Plan

1. Unit tests for new tool schema/validation.
2. DB migration and CRUD tests for `subagent_runs`.
3. End-to-end tests:
   - spawn returns accepted + run id
   - list/info visibility in same chat
   - kill transitions running/queued runs to cancelled

## Rollback Plan

1. Disable new tools in registry.
2. Keep table data; no destructive migration required.
3. Re-enable legacy behavior only if explicitly reintroduced.

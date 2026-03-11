# DrugClaw Developer Guide

## Quick start

```sh
git clone <repo-url>
cd drugclaw
cp drugclaw.config.example.yaml drugclaw.config.yaml
# Edit drugclaw.config.yaml with your credentials
cargo run -- start
```

## Prerequisites

- Rust 1.70+ (2021 edition)
- At least one enabled channel adapter (Telegram bot token from @BotFather, Discord bot token from Discord Developer Portal, Slack app/bot tokens, Feishu/Lark app credentials, or Web UI)
- A model provider API key (Anthropic or OpenAI-compatible)

No other external dependencies. SQLite is bundled via `rusqlite`.

## Project structure

```
crates/
    drugclaw-core/      # Shared error/types/text modules
    drugclaw-storage/   # SQLite + memory + usage reporting
    drugclaw-tools/     # Tool runtime primitives + sandbox
    drugclaw-channels/  # Channel abstraction boundary
    drugclaw-app/       # App support modules (logging/skills/transcribe)

src/
    main.rs              # CLI entrypoint
    runtime.rs           # Runtime bootstrap + adapter startup
    agent_engine.rs      # Shared agent loop (process_with_agent)
    llm.rs               # Provider adapters (Anthropic/OpenAI-compatible/Codex)
    web.rs               # Web API + stream endpoints
    scheduler.rs         # Scheduler + memory reflector loops
    channels/*.rs        # Concrete adapters (Telegram/Discord/Slack/Feishu)
    tools/*.rs           # Built-in tools + registry assembly
```

## Architecture overview

### Data flow

```
Platform message (via adapter)
       |
       v
    Store in SQLite (message + chat metadata)
       |
       v
    Determine response: private=always, group=@mention only
       |
       v
    Start typing indicator (tokio::spawn, every 4s)
       |
       v
    Load session or history:
       - Try loading saved session (full message state with tool blocks)
       - If session exists: append new user messages since last save
       - If no session: fall back to DB history
           - Private: last N messages
           - Group: all messages since last bot response (catch-up)
       |
       v
    Build system prompt (bot identity + memory context + chat_id)
       |
       v
    Compact if needed (messages > max_session_messages):
       - Summarize old messages via configured model provider
       - Keep recent messages verbatim
       |
       v
    Agentic loop (up to max_tool_iterations):
       1. Call provider API with messages + tool definitions
       2. If stop_reason == "tool_use" -> execute tools -> append results -> loop
       3. If stop_reason == "end_turn" -> extract text -> return
       |
       v
    Strip image base64 data, save session to SQLite
       |
       v
    Abort typing indicator
       |
       v
    Send response (split at channel limits: Telegram 4096 / Discord 2000 / Slack 4000 / Feishu 4000)
       |
       v
    Store bot response in SQLite
```

The same core loop is reused across adapters. Adding a new platform should primarily require a new ingress/egress adapter that maps platform events into the shared `process_with_agent` flow.

### Key types

| Type | Location | Description |
|------|----------|-------------|
| `AppState` | `runtime.rs` | Shared runtime state for all adapters |
| `Database` | `drugclaw_storage::db` | SQLite wrapper with `Mutex<Connection>` |
| `ToolRegistry` | `tools/mod.rs` | Holds all `Box<dyn Tool>`, dispatches by name |
| `Tool` trait | `drugclaw_tools::runtime` | `name()`, `definition()`, `execute()` |
| `LlmProvider` | `llm.rs` | Provider abstraction for Anthropic and OpenAI-compatible APIs |
| `MemoryManager` | `memory.rs` | AGENTS.md file memory reader/writer |

### Shared state

`AppState` is wrapped in `Arc` and shared:
- Telegram handler has `Arc<AppState>` via dptree dependencies
- Discord handler has `Arc<AppState>` via serenity event handler state
- Scheduler gets `Arc<AppState>` at spawn time
- Tools that need `Bot` or `Database` hold their own clones/arcs (passed at construction)

### Multi-chat permission model

- `control_chat_ids` in `drugclaw.config.yaml` defines privileged chats.
- Tool execution receives trusted caller context from `process_with_agent` (not from model-provided args).
- Non-control chats can only operate on their own `chat_id`.
- Control chats can perform cross-chat actions.
- `write_memory` with `scope: "global"` is restricted to control chats.
- Enforcement currently applies to `send_message`, scheduler tools, `export_chat`, `todo_*`, and chat-scoped memory operations.

### Database tables

**chats:**
| Column | Type | Description |
|--------|------|-------------|
| chat_id | INTEGER PK | Channel-scoped chat ID |
| chat_title | TEXT | Chat title (nullable) |
| chat_type | TEXT | "private" or "group" |
| last_message_time | TEXT | ISO 8601 timestamp |

**messages:**
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Message ID (PK with chat_id) |
| chat_id | INTEGER | Channel-scoped chat ID |
| sender_name | TEXT | Username or first name |
| content | TEXT | Message text |
| is_from_bot | INTEGER | 0 or 1 |
| timestamp | TEXT | ISO 8601 timestamp |

**scheduled_tasks:**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment task ID |
| chat_id | INTEGER | Target chat for results |
| prompt | TEXT | Instruction to execute |
| schedule_type | TEXT | "cron" or "once" |
| schedule_value | TEXT | Cron expression or ISO timestamp |
| next_run | TEXT | Next scheduled execution time |
| last_run | TEXT | Last execution time (nullable) |
| status | TEXT | "active", "paused", "completed", "cancelled" |
| created_at | TEXT | Creation timestamp |

**sessions:**
| Column | Type | Description |
|--------|------|-------------|
| chat_id | INTEGER PK | Channel-scoped chat ID |
| messages_json | TEXT | Serialized Vec<Message> JSON (full conversation state) |
| updated_at | TEXT | ISO 8601 timestamp of last save |

**task_run_logs:**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment log ID |
| task_id | INTEGER | Associated scheduled task |
| chat_id | INTEGER | Chat the task ran in |
| started_at | TEXT | Run start timestamp |
| finished_at | TEXT | Run end timestamp |
| duration_ms | INTEGER | Run duration in milliseconds |
| success | INTEGER | 0 or 1 |
| result_summary | TEXT | Summary of run result (nullable) |

## Adding a new tool

1. Create `src/tools/my_tool.rs`:

```rust
use async_trait::async_trait;
use serde_json::json;
use crate::tools::{schema_object, Tool, ToolResult};
use drugclaw_core::llm_types::ToolDefinition;

pub struct MyTool;

#[async_trait]
impl Tool for MyTool {
    fn name(&self) -> &str {
        "my_tool"
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "my_tool".into(),
            description: "What this tool does".into(),
            input_schema: schema_object(
                json!({
                    "param1": {
                        "type": "string",
                        "description": "Description of param1"
                    }
                }),
                &["param1"],
            ),
        }
    }

    async fn execute(&self, input: serde_json::Value) -> ToolResult {
        let param1 = match input.get("param1").and_then(|v| v.as_str()) {
            Some(p) => p,
            None => return ToolResult::error("Missing param1".into()),
        };
        // Do work...
        ToolResult::success(format!("Result: {param1}"))
    }
}
```

2. Add `pub mod my_tool;` to `src/tools/mod.rs`

3. Register in `ToolRegistry::new()`:
```rust
Box::new(my_tool::MyTool),
```

If your tool needs shared state (like `Bot` or `Arc<Database>`), add a constructor:
```rust
pub struct MyTool {
    db: Arc<Database>,
}

impl MyTool {
    pub fn new(db: Arc<Database>) -> Self {
        MyTool { db }
    }
}
```

And pass it in `ToolRegistry::new()`:
```rust
Box::new(my_tool::MyTool::new(db.clone())),
```

## Adding a new platform adapter

The core agent flow is already shared. New platform support should be implemented as an adapter around that core:

1. Add a new runtime module (for example `src/<platform>.rs`) that listens to platform events.
2. Normalize incoming platform messages into the canonical fields used by persistence and `process_with_agent`:
   - stable `chat_id`
   - `chat_type` (`private`/`group`-like semantics)
   - sender display name
   - text/media blocks
3. Reuse `process_with_agent(state, chat_id, sender, chat_type, override_prompt)` for inference/tool loop/session handling.
4. Implement outbound reply sending with:
   - platform length splitting policy
   - mention semantics for group/server channels
   - attachment support parity with `send_message` where applicable
5. Keep chat identity stable across restarts so `sessions`, `messages`, scheduler, and memory scopes remain consistent.
6. Enforce existing authorization boundaries (for example `control_chat_ids`) in any platform-specific entry points.
7. Add end-to-end tests to `TEST.md` mirroring existing platform suites (DM/private, group mention, reset, limits, failure handling).

## Scheduler internals

The scheduler is a `tokio::spawn` task started in `runtime::run()`. Every 60 seconds it:

1. Queries `scheduled_tasks` for rows where `status = 'active' AND next_run <= NOW()`
2. For each due task, calls `process_with_agent()` with `override_prompt = Some(task.prompt)`
3. Sends the agent's response to the task's `chat_id`
4. For cron tasks: computes next run from the cron expression and updates the row
5. For one-shot tasks: sets `status = 'completed'`

Cron expressions use the `cron` crate's 6-field format: `sec min hour dom month dow`.

## Debugging

```sh
# Verbose logging
RUST_LOG=debug cargo run -- start

# Just drugclaw logs
RUST_LOG=drugclaw=debug cargo run -- start

# Check database directly
sqlite3 drugclaw.data/runtime/drugclaw.db
sqlite> SELECT * FROM messages ORDER BY timestamp DESC LIMIT 10;
sqlite> SELECT * FROM scheduled_tasks;
sqlite> SELECT * FROM chats;
```

## Common tasks

| Task | How |
|------|-----|
| Change the model | Set `model` in `drugclaw.config.yaml` based on `llm_provider` |
| Increase context window | Set `max_history_messages: 100` in `drugclaw.config.yaml` (uses more tokens) |
| Increase tool iterations | Set `max_tool_iterations: 200` in `drugclaw.config.yaml` |
| Reset memory | Delete files under `drugclaw.data/runtime/groups/` |
| Reset all data | Delete the `drugclaw.data/` directory |
| Tune compaction threshold | Set `max_session_messages: 60` in `drugclaw.config.yaml` (higher = more context before compaction) |
| Keep more recent messages | Set `compact_keep_recent: 30` in `drugclaw.config.yaml` (more recent messages kept verbatim) |
| Reset a chat session | Send `/reset` in the chat, or: `sqlite3 drugclaw.data/runtime/drugclaw.db "DELETE FROM sessions WHERE chat_id=XXXX;"` |
| Cancel all scheduled tasks | `sqlite3 drugclaw.data/runtime/drugclaw.db "UPDATE scheduled_tasks SET status='cancelled' WHERE status='active';"` |

## Build

```sh
cargo build              # Dev build (fast compile, slow runtime)
cargo build --release    # Release build (slow compile, fast runtime)
cargo run -- start       # Run dev build
cargo run -- help        # Show CLI help
```

The release binary is fully self-contained -- no runtime dependencies, no database server, no config files beyond `drugclaw.config.yaml`.

## Dependencies

| Crate | Version | Purpose |
|-------|---------|---------|
| teloxide | 0.17 | Telegram Bot API |
| serenity | 0.12 | Discord Gateway/API |
| tokio | 1 | Async runtime |
| reqwest | 0.12 | HTTP client (Anthropic API, web fetch/search) |
| rusqlite | 0.32 | SQLite (bundled) |
| serde / serde_json | 1 | Serialization |
| async-trait | 0.1 | Async trait support |
| chrono | 0.4 | Date/time handling |
| cron | 0.13 | Cron expression parsing |
| urlencoding | 2 | URL encoding for web search |
| regex | 1 | Regex for grep tool and HTML parsing |
| glob | 0.3 | File pattern matching |
| uuid | 1 | Message ID generation |
| thiserror | 2 | Error derive macro |
| anyhow | 1 | Error propagation |
| tracing | 0.1 | Logging |

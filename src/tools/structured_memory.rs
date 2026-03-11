use async_trait::async_trait;
use serde_json::json;
use std::sync::Arc;
use tracing::info;

use crate::memory_backend::MemoryBackend;
use drugclaw_core::llm_types::ToolDefinition;
use drugclaw_storage::db::Database;

use super::{auth_context_from_input, authorize_chat_access, schema_object, Tool, ToolResult};

// ── Search ────────────────────────────────────────────────────────────────────

pub struct StructuredMemorySearchTool {
    memory_backend: Arc<MemoryBackend>,
}

impl StructuredMemorySearchTool {
    pub fn new(db: Arc<Database>, memory_backend: Arc<MemoryBackend>) -> Self {
        let _ = db;
        Self { memory_backend }
    }
}

#[async_trait]
impl Tool for StructuredMemorySearchTool {
    fn name(&self) -> &str {
        "structured_memory_search"
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "structured_memory_search".into(),
            description: "Search structured memories extracted from past conversations. Returns memories whose content contains the query string.".into(),
            input_schema: schema_object(
                json!({
                    "query": {
                        "type": "string",
                        "description": "Keyword(s) to search for in memory content"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 10, max 50)"
                    },
                    "include_archived": {
                        "type": "boolean",
                        "description": "Whether to include archived memories in results (default false)"
                    }
                }),
                &["query"],
            ),
        }
    }

    async fn execute(&self, input: serde_json::Value) -> ToolResult {
        let query = match input.get("query").and_then(|v| v.as_str()) {
            Some(q) if !q.trim().is_empty() => q.trim().to_string(),
            _ => return ToolResult::error("Missing or empty 'query' parameter".into()),
        };
        let limit = input
            .get("limit")
            .and_then(|v| v.as_u64())
            .map(|n| n.min(50) as usize)
            .unwrap_or(10);
        let include_archived = input
            .get("include_archived")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        let chat_id = auth_context_from_input(&input)
            .map(|a| a.caller_chat_id)
            .unwrap_or(0);

        info!(
            "structured_memory_search: query={query:?} chat_id={chat_id} limit={limit} include_archived={include_archived}"
        );

        match self
            .memory_backend
            .search_memories_with_options(chat_id, &query, limit, include_archived, true)
            .await
        {
            Ok(memories) if memories.is_empty() => {
                ToolResult::success("No memories found matching that query.".into())
            }
            Ok(memories) => {
                let lines: Vec<String> = memories
                    .iter()
                    .map(|m| {
                        let scope = if m.chat_id.is_none() {
                            "global"
                        } else {
                            "chat"
                        };
                        format!("[id={}] [{}] [{}] {}", m.id, m.category, scope, m.content)
                    })
                    .collect();
                ToolResult::success(lines.join("\n"))
            }
            Err(e) => ToolResult::error(format!("Search failed: {e}")),
        }
    }
}

// ── Delete ────────────────────────────────────────────────────────────────────

pub struct StructuredMemoryDeleteTool {
    memory_backend: Arc<MemoryBackend>,
}

impl StructuredMemoryDeleteTool {
    pub fn new(db: Arc<Database>, memory_backend: Arc<MemoryBackend>) -> Self {
        let _ = db;
        Self { memory_backend }
    }
}

#[async_trait]
impl Tool for StructuredMemoryDeleteTool {
    fn name(&self) -> &str {
        "structured_memory_delete"
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "structured_memory_delete".into(),
            description: "Archive a structured memory by its id (soft delete). Use structured_memory_search first to find the id. You can only archive memories that belong to the current chat or global memories if you are a control chat.".into(),
            input_schema: schema_object(
                json!({
                    "id": {
                        "type": "integer",
                        "description": "The id of the memory to delete"
                    }
                }),
                &["id"],
            ),
        }
    }

    async fn execute(&self, input: serde_json::Value) -> ToolResult {
        let id = match input.get("id").and_then(|v| v.as_i64()) {
            Some(id) => id,
            None => return ToolResult::error("Missing 'id' parameter".into()),
        };

        // Load memory first to check ownership
        let mem = match self.memory_backend.get_memory_by_id(id).await {
            Ok(Some(m)) => m,
            Ok(None) => return ToolResult::error(format!("Memory id={id} not found")),
            Err(e) => return ToolResult::error(format!("DB error: {e}")),
        };

        // Authorize: caller must own the chat or be a control chat; global memories only by control
        if let Some(auth) = auth_context_from_input(&input) {
            match mem.chat_id {
                Some(mem_chat_id) => {
                    if let Err(e) = authorize_chat_access(&input, mem_chat_id) {
                        return ToolResult::error(e);
                    }
                }
                None => {
                    // Global memory — requires control chat
                    if !auth.is_control_chat() {
                        return ToolResult::error(format!(
                            "Permission denied: only control chats can delete global memories (caller: {})",
                            auth.caller_chat_id
                        ));
                    }
                }
            }
        }

        info!("structured_memory_delete: id={id}");

        match self.memory_backend.archive_memory(id).await {
            Ok(true) => ToolResult::success(format!("Memory id={id} archived.")),
            Ok(false) => ToolResult::error(format!("Memory id={id} not found")),
            Err(e) => ToolResult::error(format!("Delete failed: {e}")),
        }
    }
}

// ── Update ────────────────────────────────────────────────────────────────────

pub struct StructuredMemoryUpdateTool {
    memory_backend: Arc<MemoryBackend>,
}

impl StructuredMemoryUpdateTool {
    pub fn new(db: Arc<Database>, memory_backend: Arc<MemoryBackend>) -> Self {
        let _ = db;
        Self { memory_backend }
    }
}

#[async_trait]
impl Tool for StructuredMemoryUpdateTool {
    fn name(&self) -> &str {
        "structured_memory_update"
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "structured_memory_update".into(),
            description: "Update the content or category of an existing structured memory. Use this to correct outdated or wrong memories instead of creating a duplicate.".into(),
            input_schema: schema_object(
                json!({
                    "id": {
                        "type": "integer",
                        "description": "The id of the memory to update"
                    },
                    "content": {
                        "type": "string",
                        "description": "New content for the memory (max 300 characters)"
                    },
                    "category": {
                        "type": "string",
                        "description": "Category: PROFILE, KNOWLEDGE, or EVENT",
                        "enum": ["PROFILE", "KNOWLEDGE", "EVENT"]
                    }
                }),
                &["id", "content"],
            ),
        }
    }

    async fn execute(&self, input: serde_json::Value) -> ToolResult {
        let id = match input.get("id").and_then(|v| v.as_i64()) {
            Some(id) => id,
            None => return ToolResult::error("Missing 'id' parameter".into()),
        };
        let content = match input.get("content").and_then(|v| v.as_str()) {
            Some(c) if !c.trim().is_empty() => c.trim().to_string(),
            _ => return ToolResult::error("Missing or empty 'content' parameter".into()),
        };
        if content.len() > 300 {
            return ToolResult::error("Content exceeds 300 character limit".into());
        }

        // Load memory first to check ownership and get current category
        let mem = match self.memory_backend.get_memory_by_id(id).await {
            Ok(Some(m)) => m,
            Ok(None) => return ToolResult::error(format!("Memory id={id} not found")),
            Err(e) => return ToolResult::error(format!("DB error: {e}")),
        };

        // Authorize same as delete
        if let Some(auth) = auth_context_from_input(&input) {
            match mem.chat_id {
                Some(mem_chat_id) => {
                    if let Err(e) = authorize_chat_access(&input, mem_chat_id) {
                        return ToolResult::error(e);
                    }
                }
                None => {
                    if !auth.is_control_chat() {
                        return ToolResult::error(format!(
                            "Permission denied: only control chats can update global memories (caller: {})",
                            auth.caller_chat_id
                        ));
                    }
                }
            }
        }

        let category = input
            .get("category")
            .and_then(|v| v.as_str())
            .unwrap_or(&mem.category)
            .to_string();

        let valid_categories = ["PROFILE", "KNOWLEDGE", "EVENT"];
        if !valid_categories.contains(&category.as_str()) {
            return ToolResult::error(format!(
                "Invalid category '{category}'. Must be one of: PROFILE, KNOWLEDGE, EVENT"
            ));
        }

        info!("structured_memory_update: id={id}");

        match self
            .memory_backend
            .update_memory_content(id, &content, &category)
            .await
        {
            Ok(true) => ToolResult::success(format!("Memory id={id} updated.")),
            Ok(false) => ToolResult::error(format!("Memory id={id} not found")),
            Err(e) => ToolResult::error(format!("Update failed: {e}")),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn test_db() -> Arc<Database> {
        let dir = std::env::temp_dir().join(format!("mc_smem_{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        Arc::new(Database::new(dir.to_str().unwrap()).unwrap())
    }

    fn test_backend(db: Arc<Database>) -> Arc<MemoryBackend> {
        Arc::new(MemoryBackend::local_only(db))
    }

    #[tokio::test]
    async fn test_search_returns_results() {
        let db = test_db();
        db.insert_memory(Some(100), "User loves Rust programming", "PROFILE")
            .unwrap();
        db.insert_memory(Some(100), "User likes coffee", "PROFILE")
            .unwrap();
        let tool = StructuredMemorySearchTool::new(db.clone(), test_backend(db));
        let result = tool
            .execute(json!({
                "query": "rust",
                "__drugclaw_auth": {"caller_chat_id": 100, "control_chat_ids": []}
            }))
            .await;
        assert!(!result.is_error);
        assert!(result.content.contains("Rust"));
        assert!(!result.content.contains("coffee"));
    }

    #[tokio::test]
    async fn test_search_empty_query_errors() {
        let db = test_db();
        let tool = StructuredMemorySearchTool::new(db.clone(), test_backend(db));
        let result = tool.execute(json!({"query": "  "})).await;
        assert!(result.is_error);
    }

    #[tokio::test]
    async fn test_delete_own_chat_memory() {
        let db = test_db();
        let id = db.insert_memory(Some(100), "to delete", "EVENT").unwrap();
        let tool = StructuredMemoryDeleteTool::new(db.clone(), test_backend(db.clone()));
        let result = tool
            .execute(json!({
                "id": id,
                "__drugclaw_auth": {"caller_chat_id": 100, "control_chat_ids": []}
            }))
            .await;
        assert!(!result.is_error, "{}", result.content);
        let mem = db.get_memory_by_id(id).unwrap().unwrap();
        assert!(mem.is_archived);
    }

    #[tokio::test]
    async fn test_delete_other_chat_denied() {
        let db = test_db();
        let id = db.insert_memory(Some(200), "other chat", "EVENT").unwrap();
        let tool = StructuredMemoryDeleteTool::new(db.clone(), test_backend(db));
        let result = tool
            .execute(json!({
                "id": id,
                "__drugclaw_auth": {"caller_chat_id": 100, "control_chat_ids": []}
            }))
            .await;
        assert!(result.is_error);
        assert!(result.content.contains("Permission denied"));
    }

    #[tokio::test]
    async fn test_update_memory() {
        let db = test_db();
        let id = db
            .insert_memory(Some(100), "User lives in Tokyo", "PROFILE")
            .unwrap();
        let tool = StructuredMemoryUpdateTool::new(db.clone(), test_backend(db.clone()));
        let result = tool
            .execute(json!({
                "id": id,
                "content": "User lives in Osaka",
                "__drugclaw_auth": {"caller_chat_id": 100, "control_chat_ids": []}
            }))
            .await;
        assert!(!result.is_error, "{}", result.content);
        let mem = db.get_memory_by_id(id).unwrap().unwrap();
        assert_eq!(mem.content, "User lives in Osaka");
    }

    #[tokio::test]
    async fn test_update_content_too_long() {
        let db = test_db();
        let id = db.insert_memory(Some(100), "short", "EVENT").unwrap();
        let tool = StructuredMemoryUpdateTool::new(db.clone(), test_backend(db));
        let long = "x".repeat(301);
        let result = tool
            .execute(json!({
                "id": id,
                "content": long,
                "__drugclaw_auth": {"caller_chat_id": 100, "control_chat_ids": []}
            }))
            .await;
        assert!(result.is_error);
        assert!(result.content.contains("300 character"));
    }
}

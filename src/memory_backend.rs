use std::collections::HashMap;
use std::sync::Arc;

use tracing::{info, warn};

use crate::mcp::{McpManager, McpServer, McpToolInfo};
use drugclaw_core::error::DrugClawError;
use drugclaw_storage::db::{call_blocking, Database, Memory};

#[derive(Clone)]
pub struct MemoryMcpClient {
    server: Arc<McpServer>,
    query_tool: String,
    upsert_tool: String,
}

impl MemoryMcpClient {
    pub fn discover(manager: &McpManager) -> Option<Self> {
        let tools = manager.all_tools();
        let mut grouped: HashMap<String, (Option<Arc<McpServer>>, bool, bool)> = HashMap::new();
        for (server, tool) in tools {
            let entry =
                grouped
                    .entry(tool.server_name.clone())
                    .or_insert((Some(server), false, false));
            if tool.name == "memory_query" {
                entry.1 = true;
            }
            if tool.name == "memory_upsert" {
                entry.2 = true;
            }
        }

        for (name, (server_opt, has_query, has_upsert)) in grouped {
            if has_query && has_upsert {
                if let Some(server) = server_opt {
                    info!("Memory MCP backend enabled via server '{name}'");
                    return Some(Self {
                        server,
                        query_tool: "memory_query".to_string(),
                        upsert_tool: "memory_upsert".to_string(),
                    });
                }
            }
        }
        None
    }

    async fn call_query(&self, payload: serde_json::Value) -> Result<serde_json::Value, String> {
        let text = self.server.call_tool(&self.query_tool, payload).await?;
        parse_json_loose(&text)
    }

    async fn call_upsert(&self, payload: serde_json::Value) -> Result<serde_json::Value, String> {
        let text = self.server.call_tool(&self.upsert_tool, payload).await?;
        parse_json_loose(&text)
    }
}

pub struct MemoryBackend {
    db: Arc<Database>,
    mcp: Option<MemoryMcpClient>,
}

impl MemoryBackend {
    pub fn new(db: Arc<Database>, mcp: Option<MemoryMcpClient>) -> Self {
        Self { db, mcp }
    }

    pub fn local_only(db: Arc<Database>) -> Self {
        Self { db, mcp: None }
    }

    pub fn prefers_mcp(&self) -> bool {
        self.mcp.is_some()
    }

    pub async fn get_all_memories_for_chat(
        &self,
        chat_id: Option<i64>,
    ) -> Result<Vec<Memory>, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "list",
                "chat_id": chat_id,
            });
            if let Ok(value) = mcp.call_query(payload).await {
                if let Some(memories) = parse_memory_list(&value) {
                    return Ok(memories);
                }
            }
            warn!("memory_query(list) failed or returned invalid payload; falling back to sqlite");
        }

        let chat = chat_id;
        call_blocking(self.db.clone(), move |db| {
            db.get_all_memories_for_chat(chat)
        })
        .await
    }

    pub async fn get_memories_for_context(
        &self,
        chat_id: i64,
        limit: usize,
    ) -> Result<Vec<Memory>, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "context",
                "chat_id": chat_id,
                "limit": limit,
            });
            if let Ok(value) = mcp.call_query(payload).await {
                if let Some(memories) = parse_memory_list(&value) {
                    return Ok(memories);
                }
            }
            warn!(
                "memory_query(context) failed or returned invalid payload; falling back to sqlite"
            );
        }

        call_blocking(self.db.clone(), move |db| {
            db.get_memories_for_context(chat_id, limit)
        })
        .await
    }

    pub async fn search_memories_with_options(
        &self,
        chat_id: i64,
        query: &str,
        limit: usize,
        include_archived: bool,
        broad_recall: bool,
    ) -> Result<Vec<Memory>, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "search",
                "chat_id": chat_id,
                "query": query,
                "limit": limit,
                "include_archived": include_archived,
                "broad_recall": broad_recall,
            });
            if let Ok(value) = mcp.call_query(payload).await {
                if let Some(memories) = parse_memory_list(&value) {
                    return Ok(memories);
                }
            }
            warn!(
                "memory_query(search) failed or returned invalid payload; falling back to sqlite"
            );
        }

        let q = query.to_string();
        call_blocking(self.db.clone(), move |db| {
            db.search_memories_with_options(chat_id, &q, limit, include_archived, broad_recall)
        })
        .await
    }

    pub async fn get_memory_by_id(&self, id: i64) -> Result<Option<Memory>, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "get",
                "id": id,
            });
            if let Ok(value) = mcp.call_query(payload).await {
                if let Some(memories) = parse_memory_list(&value) {
                    return Ok(memories.into_iter().next());
                }
                if let Some(memory) = parse_single_memory(&value) {
                    return Ok(Some(memory));
                }
            }
            warn!("memory_query(get) failed or returned invalid payload; falling back to sqlite");
        }

        call_blocking(self.db.clone(), move |db| db.get_memory_by_id(id)).await
    }

    pub async fn insert_memory_with_metadata(
        &self,
        chat_id: Option<i64>,
        content: &str,
        category: &str,
        source: &str,
        confidence: f64,
    ) -> Result<i64, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "insert",
                "chat_id": chat_id,
                "content": content,
                "category": category,
                "source": source,
                "confidence": confidence,
            });
            if let Ok(value) = mcp.call_upsert(payload).await {
                if let Some(id) = extract_id(&value) {
                    return Ok(id);
                }
            }
            warn!(
                "memory_upsert(insert) failed or returned invalid payload; falling back to sqlite"
            );
        }

        let text = content.to_string();
        let cat = category.to_string();
        let src = source.to_string();
        call_blocking(self.db.clone(), move |db| {
            db.insert_memory_with_metadata(chat_id, &text, &cat, &src, confidence)
        })
        .await
    }

    pub async fn update_memory_with_metadata(
        &self,
        id: i64,
        content: &str,
        category: &str,
        confidence: f64,
        source: &str,
    ) -> Result<bool, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "update",
                "id": id,
                "content": content,
                "category": category,
                "source": source,
                "confidence": confidence,
            });
            if let Ok(value) = mcp.call_upsert(payload).await {
                if let Some(updated) = extract_bool_flag(&value) {
                    return Ok(updated);
                }
            }
            warn!(
                "memory_upsert(update) failed or returned invalid payload; falling back to sqlite"
            );
        }

        let text = content.to_string();
        let cat = category.to_string();
        let src = source.to_string();
        call_blocking(self.db.clone(), move |db| {
            db.update_memory_with_metadata(id, &text, &cat, confidence, &src)
        })
        .await
    }

    pub async fn update_memory_content(
        &self,
        id: i64,
        content: &str,
        category: &str,
    ) -> Result<bool, DrugClawError> {
        self.update_memory_with_metadata(id, content, category, 0.8, "tool")
            .await
    }

    pub async fn archive_memory(&self, id: i64) -> Result<bool, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "archive",
                "id": id,
            });
            if let Ok(value) = mcp.call_upsert(payload).await {
                if let Some(updated) = extract_bool_flag(&value) {
                    return Ok(updated);
                }
            }
            warn!(
                "memory_upsert(archive) failed or returned invalid payload; falling back to sqlite"
            );
        }

        call_blocking(self.db.clone(), move |db| db.archive_memory(id)).await
    }

    pub async fn supersede_memory(
        &self,
        from_memory_id: i64,
        new_content: &str,
        category: &str,
        source: &str,
        confidence: f64,
        reason: Option<&str>,
    ) -> Result<i64, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "supersede",
                "from_memory_id": from_memory_id,
                "content": new_content,
                "category": category,
                "source": source,
                "confidence": confidence,
                "reason": reason,
            });
            if let Ok(value) = mcp.call_upsert(payload).await {
                if let Some(id) = extract_id(&value) {
                    return Ok(id);
                }
            }
            warn!("memory_upsert(supersede) failed or returned invalid payload; falling back to sqlite");
        }

        let text = new_content.to_string();
        let cat = category.to_string();
        let src = source.to_string();
        let why = reason.map(|v| v.to_string());
        call_blocking(self.db.clone(), move |db| {
            db.supersede_memory(
                from_memory_id,
                &text,
                &cat,
                &src,
                confidence,
                why.as_deref(),
            )
        })
        .await
    }

    pub async fn touch_memory_last_seen(
        &self,
        id: i64,
        confidence_floor: Option<f64>,
    ) -> Result<bool, DrugClawError> {
        if let Some(mcp) = &self.mcp {
            let payload = serde_json::json!({
                "op": "touch",
                "id": id,
                "confidence_floor": confidence_floor,
            });
            if let Ok(value) = mcp.call_upsert(payload).await {
                if let Some(updated) = extract_bool_flag(&value) {
                    return Ok(updated);
                }
            }
            warn!(
                "memory_upsert(touch) failed or returned invalid payload; falling back to sqlite"
            );
        }

        call_blocking(self.db.clone(), move |db| {
            db.touch_memory_last_seen(id, confidence_floor)
        })
        .await
    }
}

fn parse_json_loose(text: &str) -> Result<serde_json::Value, String> {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(text) {
        return Ok(v);
    }
    for (open, close) in [(b'[', b']'), (b'{', b'}')] {
        if let Some(start) = text.as_bytes().iter().position(|b| *b == open) {
            if let Some(end) = text.as_bytes().iter().rposition(|b| *b == close) {
                if start < end {
                    if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text[start..=end]) {
                        return Ok(v);
                    }
                }
            }
        }
    }
    Err("MCP memory response is not valid JSON".to_string())
}

fn parse_memory_list(value: &serde_json::Value) -> Option<Vec<Memory>> {
    if let Some(arr) = value.as_array() {
        return Some(arr.iter().filter_map(parse_single_memory).collect());
    }
    let obj = value.as_object()?;
    if let Some(arr) = obj.get("memories").and_then(|v| v.as_array()) {
        return Some(arr.iter().filter_map(parse_single_memory).collect());
    }
    if let Some(arr) = obj.get("items").and_then(|v| v.as_array()) {
        return Some(arr.iter().filter_map(parse_single_memory).collect());
    }
    None
}

fn parse_single_memory(value: &serde_json::Value) -> Option<Memory> {
    let obj = value.as_object()?;
    let id = obj.get("id").and_then(|v| v.as_i64())?;
    let content = obj.get("content").and_then(|v| v.as_str())?.to_string();
    let category = obj
        .get("category")
        .and_then(|v| v.as_str())
        .unwrap_or("KNOWLEDGE")
        .to_string();
    let now = chrono::Utc::now().to_rfc3339();
    Some(Memory {
        id,
        chat_id: obj.get("chat_id").and_then(|v| v.as_i64()),
        content,
        category,
        created_at: obj
            .get("created_at")
            .and_then(|v| v.as_str())
            .unwrap_or(&now)
            .to_string(),
        updated_at: obj
            .get("updated_at")
            .and_then(|v| v.as_str())
            .unwrap_or(&now)
            .to_string(),
        embedding_model: obj
            .get("embedding_model")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
        confidence: obj
            .get("confidence")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.8),
        source: obj
            .get("source")
            .and_then(|v| v.as_str())
            .unwrap_or("mcp_memory")
            .to_string(),
        last_seen_at: obj
            .get("last_seen_at")
            .and_then(|v| v.as_str())
            .unwrap_or(&now)
            .to_string(),
        is_archived: obj
            .get("is_archived")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
        archived_at: obj
            .get("archived_at")
            .and_then(|v| v.as_str())
            .map(|v| v.to_string()),
    })
}

fn extract_id(value: &serde_json::Value) -> Option<i64> {
    value
        .get("id")
        .and_then(|v| v.as_i64())
        .or_else(|| value.get("memory_id").and_then(|v| v.as_i64()))
        .or_else(|| {
            value
                .get("memory")
                .and_then(|v| v.get("id"))
                .and_then(|v| v.as_i64())
        })
}

fn extract_bool_flag(value: &serde_json::Value) -> Option<bool> {
    value
        .get("updated")
        .and_then(|v| v.as_bool())
        .or_else(|| value.get("ok").and_then(|v| v.as_bool()))
        .or_else(|| value.get("success").and_then(|v| v.as_bool()))
}

#[allow(dead_code)]
fn _extract_tool_info(tools: &[McpToolInfo]) -> Vec<String> {
    tools.iter().map(|t| t.name.clone()).collect()
}

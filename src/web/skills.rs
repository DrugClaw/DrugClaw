use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    Json,
};
use serde::Serialize;
use serde_json::json;

use crate::web::{middleware::AuthScope, require_scope, WebState};

#[derive(Debug, Serialize)]
struct SkillStatus {
    name: String,
    description: String,
    enabled: bool,
    source: String,
    version: Option<String>,
    platforms: Vec<String>,
    reason: Option<String>,
}

pub async fn api_list_skills(
    headers: HeaderMap,
    State(state): State<WebState>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    require_scope(&state, &headers, AuthScope::Read).await?;

    let skills = state.app_state.skills.discover_skills_with_status(true);
    let mut result = Vec::new();

    for skill in skills {
        result.push(SkillStatus {
            name: skill.meta.name,
            description: skill.meta.description,
            enabled: skill.available,
            source: skill.meta.source,
            version: skill.meta.version,
            platforms: skill.meta.platforms,
            reason: skill.reason,
        });
    }

    Ok(Json(json!({
        "ok": true,
        "skills": result
    })))
}

pub async fn api_enable_skill(
    headers: HeaderMap,
    Path(name): Path<String>,
    State(state): State<WebState>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    require_scope(&state, &headers, AuthScope::Write).await?;

    if !state.app_state.skills.has_skill(&name) {
        return Err((StatusCode::NOT_FOUND, "Skill not found".into()));
    }

    state
        .app_state
        .skills
        .set_enabled(&name, true)
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e))?;

    Ok(Json(json!({"ok": true, "message": "Skill enabled"})))
}

pub async fn api_disable_skill(
    headers: HeaderMap,
    Path(name): Path<String>,
    State(state): State<WebState>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    require_scope(&state, &headers, AuthScope::Write).await?;

    if !state.app_state.skills.has_skill(&name) {
        return Err((StatusCode::NOT_FOUND, "Skill not found".into()));
    }

    state
        .app_state
        .skills
        .set_enabled(&name, false)
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e))?;

    Ok(Json(json!({"ok": true, "message": "Skill disabled"})))
}

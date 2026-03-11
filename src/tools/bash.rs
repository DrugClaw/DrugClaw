use async_trait::async_trait;
use serde_json::json;
use std::collections::HashMap;
use std::path::Path;
use std::path::PathBuf;
use std::sync::Arc;
use tracing::info;

use crate::config::WorkingDirIsolation;
use drugclaw_core::llm_types::ToolDefinition;
use drugclaw_core::text::floor_char_boundary;
use drugclaw_tools::sandbox::{SandboxExecOptions, SandboxRouter};

use super::{schema_object, Tool, ToolResult};

pub struct BashTool {
    working_dir: PathBuf,
    working_dir_isolation: WorkingDirIsolation,
    default_timeout_secs: u64,
    sandbox_router: Option<Arc<SandboxRouter>>,
}

impl BashTool {
    pub fn new(working_dir: &str) -> Self {
        Self::new_with_isolation(working_dir, WorkingDirIsolation::Shared)
    }

    pub fn new_with_isolation(
        working_dir: &str,
        working_dir_isolation: WorkingDirIsolation,
    ) -> Self {
        Self {
            working_dir: PathBuf::from(working_dir),
            working_dir_isolation,
            default_timeout_secs: 120,
            sandbox_router: None,
        }
    }

    pub fn with_default_timeout_secs(mut self, timeout_secs: u64) -> Self {
        self.default_timeout_secs = timeout_secs;
        self
    }

    pub fn with_sandbox_router(mut self, router: Arc<SandboxRouter>) -> Self {
        self.sandbox_router = Some(router);
        self
    }
}

fn extract_env_files(input: &serde_json::Value) -> Vec<PathBuf> {
    super::auth_context_from_input(input)
        .map(|auth| auth.env_files.iter().map(PathBuf::from).collect())
        .unwrap_or_default()
}

const REDACT_MIN_VALUE_LEN: usize = 8;

fn redact_env_secrets(output: &str, env_files: &[PathBuf]) -> String {
    let mut secrets: Vec<(String, String)> = Vec::new();
    for env_file in env_files {
        if let Ok(content) = std::fs::read_to_string(env_file) {
            for (key, value) in drugclaw_tools::env_file::parse_dotenv(&content) {
                if value.len() >= REDACT_MIN_VALUE_LEN {
                    secrets.push((key, value));
                }
            }
        }
    }
    if secrets.is_empty() {
        return output.to_string();
    }
    secrets.sort_by(|a, b| b.1.len().cmp(&a.1.len()));
    let mut redacted = output.to_string();
    for (key, value) in &secrets {
        redacted = redacted.replace(value, &format!("[REDACTED:{key}]"));
    }
    redacted
}

fn path_boundary_before(prev: Option<char>) -> bool {
    prev.is_none()
        || matches!(
            prev,
            Some(' ' | '\t' | '\n' | '\'' | '"' | '=' | '(' | ':' | ';' | '|')
        )
}

fn contains_explicit_tmp_absolute_path(command: &str) -> bool {
    let mut start = 0usize;
    while let Some(offset) = command[start..].find("/tmp/") {
        let idx = start + offset;
        let prev = if idx == 0 {
            None
        } else {
            command[..idx].chars().next_back()
        };
        if path_boundary_before(prev) {
            return true;
        }
        start = idx + 5;
    }
    false
}

fn normalize_tmp_absolute_paths(command: &str) -> Option<String> {
    let mut normalized = String::with_capacity(command.len());
    let mut changed = false;
    let mut cursor = 0usize;

    while let Some(offset) = command[cursor..].find("/tmp/") {
        let idx = cursor + offset;
        let prev = if idx == 0 {
            None
        } else {
            command[..idx].chars().next_back()
        };
        if !path_boundary_before(prev) {
            normalized.push_str(&command[cursor..idx + 5]);
            cursor = idx + 5;
            continue;
        }

        normalized.push_str(&command[cursor..idx]);
        normalized.push_str("./");
        cursor = idx + 5;
        changed = true;
    }

    if !changed {
        return None;
    }

    normalized.push_str(&command[cursor..]);
    Some(normalized)
}

fn normalize_default_working_dir_aliases(command: &str) -> Option<String> {
    let patterns = [
        "~/.drugclaw/working_dir/",
        "$HOME/.drugclaw/working_dir/",
        "${HOME}/.drugclaw/working_dir/",
    ];
    let mut normalized = command.to_string();
    let mut changed = false;
    for pattern in patterns {
        if normalized.contains(pattern) {
            normalized = normalized.replace(pattern, "$DRUGCLAW_WORKDIR_ROOT/");
            changed = true;
        }
    }
    changed.then_some(normalized)
}

fn normalize_bash_command(command: &str) -> (String, bool) {
    let mut normalized = command.to_string();
    let mut changed = false;

    if let Some(next) = normalize_default_working_dir_aliases(&normalized) {
        normalized = next;
        changed = true;
    }
    if let Some(next) = normalize_tmp_absolute_paths(&normalized) {
        normalized = next;
        changed = true;
    }

    (normalized, changed)
}

fn shell_home_dir() -> Option<String> {
    std::env::var("HOME")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .or_else(|| {
            std::env::var("USERPROFILE")
                .ok()
                .filter(|v| !v.trim().is_empty())
        })
}

fn build_shell_env(working_dir: &Path, working_dir_root: &Path) -> HashMap<String, String> {
    let mut envs = HashMap::new();
    let working_dir_str = working_dir.to_string_lossy().to_string();
    envs.insert("DRUGCLAW_TMP_DIR".to_string(), working_dir_str.clone());
    envs.insert("DRUGCLAW_WORKDIR".to_string(), working_dir_str.clone());
    envs.insert("TMPDIR".to_string(), working_dir_str.clone());
    envs.insert("TMP".to_string(), working_dir_str.clone());
    envs.insert("TEMP".to_string(), working_dir_str.clone());
    envs.insert(
        "DRUGCLAW_WORKDIR_ROOT".to_string(),
        working_dir_root.to_string_lossy().to_string(),
    );
    if let Some(home) = shell_home_dir() {
        envs.insert("HOME".to_string(), home);
    }
    envs
}

fn command_accesses_dotenv(command: &str) -> bool {
    let patterns = [".env", "dotenv", "env_file"];
    let lower = command.to_ascii_lowercase();
    patterns.iter().any(|p| lower.contains(p))
}

#[async_trait]
impl Tool for BashTool {
    fn name(&self) -> &str {
        "bash"
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: "bash".into(),
            description: "Execute a bash command and return the output. IMPORTANT: You must CALL this tool (not write it as text) to run a command. Commands already start inside the current chat working directory's tmp workspace, so prefer relative paths like `file.txt` or `./script.py` instead of `/tmp/...` or `~/.drugclaw/...`.".into(),
            input_schema: schema_object(
                json!({
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute. The current working directory is already the chat tmp workspace. Prefer relative paths; `DRUGCLAW_TMP_DIR`, `DRUGCLAW_WORKDIR`, and `DRUGCLAW_WORKDIR_ROOT` are available."
                    },
                    "timeout_secs": {
                        "type": "integer",
                        "description": "Timeout in seconds (defaults to configured tool timeout budget)"
                    }
                }),
                &["command"],
            ),
        }
    }

    async fn execute(&self, input: serde_json::Value) -> ToolResult {
        let command = match input.get("command").and_then(|v| v.as_str()) {
            Some(c) => c,
            None => return ToolResult::error("Missing 'command' parameter".into()),
        };

        let timeout_secs = input
            .get("timeout_secs")
            .and_then(|v| v.as_u64())
            .unwrap_or(self.default_timeout_secs);
        let working_dir_root =
            super::resolve_tool_working_dir(&self.working_dir, self.working_dir_isolation, &input);
        let working_dir = working_dir_root.join("tmp");
        if let Err(e) = tokio::fs::create_dir_all(&working_dir).await {
            return ToolResult::error(format!(
                "Failed to create working directory {}: {e}",
                working_dir.display()
            ));
        }

        let (command, normalized_paths) = normalize_bash_command(command);
        if contains_explicit_tmp_absolute_path(&command) {
            return ToolResult::error(format!(
                "Command contains absolute /tmp path, which is disallowed. Bash already starts in the current chat working directory: {}. Use relative paths like `./file` or `$DRUGCLAW_TMP_DIR/file`.",
                working_dir.display()
            ))
            .with_error_type("path_policy_blocked");
        }

        let env_files = extract_env_files(&input);
        if !env_files.is_empty() && command_accesses_dotenv(&command) {
            return ToolResult::error(
                "Command appears to access .env files, which is blocked for security. Skill environment variables are already injected automatically.".into(),
            )
            .with_error_type("env_access_blocked");
        }

        if normalized_paths {
            info!(
                "Normalized bash command paths for working dir {}: {}",
                working_dir.display(),
                command
            );
        }
        info!("Executing bash in {}: {}", working_dir.display(), command);

        let session_key = super::auth_context_from_input(&input)
            .map(|auth| format!("{}-{}", auth.caller_channel, auth.caller_chat_id))
            .unwrap_or_else(|| "shared".to_string());
        let env_files_for_redact = env_files.clone();
        let exec_opts = SandboxExecOptions {
            timeout: std::time::Duration::from_secs(timeout_secs),
            working_dir: Some(working_dir.clone()),
            envs: build_shell_env(&working_dir, &working_dir_root),
            env_files,
        };
        let result = if let Some(router) = &self.sandbox_router {
            router.exec(&session_key, &command, &exec_opts).await
        } else {
            drugclaw_tools::sandbox::exec_host_command(&command, &exec_opts).await
        };

        match result {
            Ok(output) => {
                let stdout = output.stdout;
                let stderr = output.stderr;
                let exit_code = output.exit_code;

                let mut result_text = String::new();
                if !stdout.is_empty() {
                    result_text.push_str(stdout.as_str());
                }
                if !stderr.is_empty() {
                    if !result_text.is_empty() {
                        result_text.push('\n');
                    }
                    result_text.push_str("STDERR:\n");
                    result_text.push_str(stderr.as_str());
                }
                if result_text.is_empty() {
                    result_text = format!("Command completed with exit code {exit_code}");
                }

                result_text = redact_env_secrets(&result_text, &env_files_for_redact);

                // Truncate very long output
                if result_text.len() > 30000 {
                    let cutoff = floor_char_boundary(&result_text, 30000);
                    result_text.truncate(cutoff);
                    result_text.push_str("\n... (output truncated)");
                }

                if exit_code == 0 {
                    ToolResult::success(result_text).with_status_code(exit_code)
                } else {
                    ToolResult::error(format!("Exit code {exit_code}\n{result_text}"))
                        .with_status_code(exit_code)
                        .with_error_type("process_exit")
                }
            }
            Err(e) => {
                let msg = e.to_string();
                if msg.contains("timed out after") {
                    ToolResult::error(format!("Command timed out after {timeout_secs} seconds"))
                        .with_error_type("timeout")
                } else {
                    ToolResult::error(format!("Failed to execute command: {e}"))
                        .with_error_type("spawn_error")
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sleep_command(seconds: u64) -> String {
        if cfg!(target_os = "windows") {
            format!("Start-Sleep -Seconds {seconds}")
        } else {
            format!("sleep {seconds}")
        }
    }

    fn stderr_command() -> &'static str {
        if cfg!(target_os = "windows") {
            "[Console]::Error.WriteLine('err')"
        } else {
            "echo err >&2"
        }
    }

    fn write_marker_command(file_name: &str) -> String {
        if cfg!(target_os = "windows") {
            format!("New-Item -ItemType File -Path '{file_name}' -Force | Out-Null")
        } else {
            format!("touch '{file_name}'")
        }
    }

    fn echo_env_command(var_name: &str) -> String {
        if cfg!(target_os = "windows") {
            format!("$env:{var_name}")
        } else {
            format!("echo ${var_name}")
        }
    }

    #[test]
    fn test_contains_explicit_tmp_absolute_path_detection() {
        assert!(contains_explicit_tmp_absolute_path("ls /tmp/x"));
        assert!(contains_explicit_tmp_absolute_path("A=\"/tmp/x\"; echo $A"));
        assert!(!contains_explicit_tmp_absolute_path(
            "ls /Users/eevv/work/project/tmp/x"
        ));
    }

    #[test]
    fn test_normalize_bash_command_rewrites_common_workspace_aliases() {
        let (normalized, changed) = normalize_bash_command(
            "cd ~/.drugclaw/working_dir/chat/telegram/42/tmp && pymol -cq /tmp/render.py",
        );
        assert!(changed);
        assert_eq!(
            normalized,
            "cd $DRUGCLAW_WORKDIR_ROOT/chat/telegram/42/tmp && pymol -cq ./render.py"
        );
    }

    #[tokio::test]
    async fn test_bash_echo() {
        let tool = BashTool::new(".");
        let result = tool.execute(json!({"command": "echo hello"})).await;
        assert!(!result.is_error);
        assert!(result.content.contains("hello"));
    }

    #[tokio::test]
    async fn test_bash_exit_code_nonzero() {
        let tool = BashTool::new(".");
        let result = tool.execute(json!({"command": "exit 1"})).await;
        assert!(result.is_error);
        assert!(result.content.contains("Exit code 1"));
    }

    #[tokio::test]
    async fn test_bash_stderr() {
        let tool = BashTool::new(".");
        let result = tool.execute(json!({"command": stderr_command()})).await;
        assert!(!result.is_error); // exit code is 0
        assert!(result.content.contains("STDERR"));
        assert!(result.content.contains("err"));
    }

    #[tokio::test]
    async fn test_bash_timeout() {
        let tool = BashTool::new(".");
        let result = tool
            .execute(json!({"command": sleep_command(10), "timeout_secs": 1}))
            .await;
        assert!(result.is_error);
        assert!(result.content.contains("timed out"));
    }

    #[tokio::test]
    async fn test_bash_rewrites_tmp_absolute_path_into_workspace() {
        let root = std::env::temp_dir().join(format!("drugclaw_bash_{}", uuid::Uuid::new_v4()));
        let work = root.join("workspace");
        std::fs::create_dir_all(&work).unwrap();

        let tool = BashTool::new(work.to_str().unwrap());
        let result = tool
            .execute(json!({"command": "touch /tmp/from_tmp_alias.txt"}))
            .await;
        assert!(
            !result.is_error,
            "expected success, got: {}",
            result.content
        );
        assert!(work.join("shared/tmp/from_tmp_alias.txt").exists());

        let _ = std::fs::remove_dir_all(&root);
    }

    #[tokio::test]
    async fn test_bash_missing_command() {
        let tool = BashTool::new(".");
        let result = tool.execute(json!({})).await;
        assert!(result.is_error);
        assert!(result.content.contains("Missing 'command'"));
    }

    #[test]
    fn test_bash_tool_name_and_definition() {
        let tool = BashTool::new(".");
        assert_eq!(tool.name(), "bash");
        let def = tool.definition();
        assert_eq!(def.name, "bash");
        assert!(!def.description.is_empty());
        assert!(def.input_schema["properties"]["command"].is_object());
    }

    #[tokio::test]
    async fn test_bash_uses_working_dir() {
        let root = std::env::temp_dir().join(format!("drugclaw_bash_{}", uuid::Uuid::new_v4()));
        let work = root.join("workspace");
        std::fs::create_dir_all(&work).unwrap();

        let tool = BashTool::new(work.to_str().unwrap());
        let marker = "cwd_marker.txt";
        let result = tool
            .execute(json!({"command": write_marker_command(marker)}))
            .await;
        assert!(!result.is_error);

        let expected_marker = work.join("shared").join("tmp").join(marker);
        assert!(expected_marker.exists());

        let _ = std::fs::remove_dir_all(&root);
    }

    #[tokio::test]
    async fn test_bash_chat_isolation_uses_chat_working_dir() {
        let root = std::env::temp_dir().join(format!("drugclaw_bash_{}", uuid::Uuid::new_v4()));
        let work = root.join("workspace");
        std::fs::create_dir_all(&work).unwrap();

        let tool = BashTool::new_with_isolation(work.to_str().unwrap(), WorkingDirIsolation::Chat);
        let marker = "chat_marker.txt";
        let result = tool
            .execute(json!({
                "command": write_marker_command(marker),
                "__drugclaw_auth": {
                    "caller_channel": "telegram",
                    "caller_chat_id": -100123,
                    "control_chat_ids": []
                }
            }))
            .await;
        assert!(!result.is_error);

        let expected_marker = work
            .join("chat")
            .join("telegram")
            .join("neg100123")
            .join("tmp")
            .join(marker);
        assert!(expected_marker.exists());

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn test_extract_env_files_from_input() {
        let input = json!({
            "command": "echo hi",
            "__drugclaw_auth": {
                "caller_channel": "telegram",
                "caller_chat_id": 1,
                "control_chat_ids": [],
                "env_files": [
                    "/home/user/.drugclaw/skills/outline/.env",
                    "/home/user/.drugclaw/skills/weather/.env"
                ]
            }
        });
        let files = extract_env_files(&input);
        assert_eq!(files.len(), 2);
        assert_eq!(
            files[0],
            PathBuf::from("/home/user/.drugclaw/skills/outline/.env")
        );
    }

    #[test]
    fn test_extract_env_files_empty_when_absent() {
        let input = json!({"command": "echo hi"});
        let files = extract_env_files(&input);
        assert!(files.is_empty());
    }

    #[tokio::test]
    async fn test_bash_injects_env_files_into_execution() {
        let root = std::env::temp_dir().join(format!("drugclaw_bash_env_{}", uuid::Uuid::new_v4()));
        let work = root.join("workspace");
        std::fs::create_dir_all(&work).unwrap();

        let env_dir = root.join("skill_env");
        std::fs::create_dir_all(&env_dir).unwrap();
        let env_file = env_dir.join(".env");
        std::fs::write(&env_file, "TEST_SKILL_VAR=skill_value_42\n").unwrap();

        let tool = BashTool::new(work.to_str().unwrap());
        let result = tool
            .execute(json!({
                "command": echo_env_command("TEST_SKILL_VAR"),
                "__drugclaw_auth": {
                    "caller_channel": "telegram",
                    "caller_chat_id": 1,
                    "control_chat_ids": [],
                    "env_files": [env_file.to_string_lossy()]
                }
            }))
            .await;
        assert!(!result.is_error);
        assert!(
            result.content.contains("[REDACTED:TEST_SKILL_VAR]"),
            "expected redacted output, got: {}",
            result.content
        );
        assert!(!result.content.contains("skill_value_42"));

        let _ = std::fs::remove_dir_all(&root);
    }

    #[tokio::test]
    async fn test_bash_injects_workspace_env_vars() {
        let root = std::env::temp_dir().join(format!("drugclaw_bash_env_{}", uuid::Uuid::new_v4()));
        let work = root.join("workspace");
        std::fs::create_dir_all(&work).unwrap();

        let tool = BashTool::new(work.to_str().unwrap());
        let result = tool
            .execute(json!({"command": echo_env_command("DRUGCLAW_TMP_DIR")}))
            .await;
        assert!(
            !result.is_error,
            "expected success, got: {}",
            result.content
        );
        assert_eq!(
            result.content.trim(),
            work.join("shared").join("tmp").to_string_lossy()
        );

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn test_redact_env_secrets_replaces_values() {
        let dir = std::env::temp_dir().join(format!("drugclaw_redact_{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        let env_file = dir.join(".env");
        std::fs::write(&env_file, "API_KEY=supersecretkey123\nSHORT=ab\n").unwrap();

        let output = "Response: supersecretkey123 is the key";
        let redacted = redact_env_secrets(output, &[env_file]);
        assert!(redacted.contains("[REDACTED:API_KEY]"));
        assert!(!redacted.contains("supersecretkey123"));
        assert!(!redacted.contains("[REDACTED:SHORT]"));

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_redact_env_secrets_no_env_files() {
        let output = "some output text";
        let redacted = redact_env_secrets(output, &[]);
        assert_eq!(redacted, output);
    }

    #[test]
    fn test_command_accesses_dotenv_detection() {
        assert!(command_accesses_dotenv("cat .env"));
        assert!(command_accesses_dotenv("cat /path/to/.env.local"));
        assert!(command_accesses_dotenv("source dotenv"));
        assert!(!command_accesses_dotenv("echo hello"));
        assert!(!command_accesses_dotenv("ls -la"));
    }

    #[tokio::test]
    async fn test_bash_blocks_dotenv_access_when_env_files_active() {
        let tool = BashTool::new(".");
        let result = tool
            .execute(json!({
                "command": "cat .env",
                "__drugclaw_auth": {
                    "caller_channel": "telegram",
                    "caller_chat_id": 1,
                    "control_chat_ids": [],
                    "env_files": ["/some/skill/.env"]
                }
            }))
            .await;
        assert!(result.is_error);
        assert_eq!(result.error_type.as_deref(), Some("env_access_blocked"));
    }

    #[tokio::test]
    async fn test_bash_allows_dotenv_mention_without_env_files() {
        let tool = BashTool::new(".");
        let result = tool
            .execute(json!({
                "command": "echo .env is a file"
            }))
            .await;
        assert!(!result.is_error);
    }
}

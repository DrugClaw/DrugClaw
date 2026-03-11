use std::collections::VecDeque;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use tauri::State;

const MAX_LOG_LINES: usize = 4000;
const MEMORY_SQL: &str = "SELECT id, chat_id, chat_channel, external_chat_id, category, embedding_model FROM memories ORDER BY id DESC LIMIT 20;";

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LogEntry {
    timestamp: String,
    stream: String,
    line: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CommandRunResult {
    command: String,
    success: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SaveConfigResult {
    config_path: String,
    resolved_data_dir: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct StepDetectionResult {
    has_config: bool,
    config_path: String,
    resolved_data_dir: String,
    build_ready: bool,
    init_ready: bool,
    query_ready: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    running: bool,
    pid: Option<u32>,
    uptime_seconds: Option<u64>,
    started_at: Option<String>,
}

impl RuntimeStatus {
    fn stopped() -> Self {
        Self {
            running: false,
            pid: None,
            uptime_seconds: None,
            started_at: None,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ConfigDraft {
    data_dir: String,
    llm_provider: String,
    llm_base_url: String,
    api_key: String,
    model: String,
    web_host: String,
    web_port: u16,
    channels: ChannelDraft,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ChannelDraft {
    web_enabled: bool,
    telegram_enabled: bool,
    telegram_bot_token: String,
    telegram_bot_username: String,
    discord_enabled: bool,
    discord_bot_token: String,
    discord_allowed_channels: String,
    slack_enabled: bool,
    slack_bot_token: String,
    slack_app_token: String,
    slack_allowed_channels: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LoadedConfigResult {
    found: bool,
    config_path: String,
    resolved_data_dir: String,
    draft: Option<ConfigDraft>,
}

#[derive(Debug, Serialize)]
struct FileConfig {
    llm_provider: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    llm_base_url: Option<String>,
    api_key: String,
    model: String,
    data_dir: String,
    working_dir: String,
    channels: FileChannels,
    web_host: String,
    web_port: u16,
}

#[derive(Debug, Serialize)]
struct FileChannels {
    web: FileWebChannel,
    telegram: FileTelegramChannel,
    discord: FileDiscordChannel,
    slack: FileSlackChannel,
}

#[derive(Debug, Serialize)]
struct FileWebChannel {
    enabled: bool,
}

#[derive(Debug, Serialize)]
struct FileTelegramChannel {
    enabled: bool,
    #[serde(skip_serializing_if = "string_is_blank")]
    bot_token: String,
    #[serde(skip_serializing_if = "string_is_blank")]
    bot_username: String,
}

#[derive(Debug, Serialize)]
struct FileDiscordChannel {
    enabled: bool,
    #[serde(skip_serializing_if = "string_is_blank")]
    bot_token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    allowed_channels: Option<Vec<u64>>,
}

#[derive(Debug, Serialize)]
struct FileSlackChannel {
    enabled: bool,
    #[serde(skip_serializing_if = "string_is_blank")]
    bot_token: String,
    #[serde(skip_serializing_if = "string_is_blank")]
    app_token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    allowed_channels: Option<Vec<String>>,
}

struct RuntimeProcess {
    child: Arc<Mutex<Child>>,
    pid: u32,
    started_at: chrono::DateTime<chrono::Utc>,
    started_instant: Instant,
}

struct AppState {
    runtime: Mutex<Option<RuntimeProcess>>,
    logs: Arc<Mutex<VecDeque<LogEntry>>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            runtime: Mutex::new(None),
            logs: Arc::new(Mutex::new(VecDeque::new())),
        }
    }
}

fn string_is_blank(input: &String) -> bool {
    input.trim().is_empty()
}

fn append_log(logs: &Arc<Mutex<VecDeque<LogEntry>>>, stream: &str, line: impl Into<String>) {
    let mut line = line.into();
    if line.ends_with('\n') {
        line = line.trim_end_matches('\n').to_string();
    }
    if line.trim().is_empty() {
        return;
    }

    let mut guard = match logs.lock() {
        Ok(guard) => guard,
        Err(_) => return,
    };
    if guard.len() >= MAX_LOG_LINES {
        guard.pop_front();
    }
    guard.push_back(LogEntry {
        timestamp: Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true),
        stream: stream.to_string(),
        line,
    });
}

fn parse_u64_csv(input: &str) -> Vec<u64> {
    input
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .filter_map(|item| item.parse::<u64>().ok())
        .collect()
}

fn parse_string_csv(input: &str) -> Vec<String> {
    input
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn expand_tilde(raw: &str) -> PathBuf {
    let trimmed = raw.trim();
    if trimmed == "~" {
        return dirs::home_dir().unwrap_or_else(|| PathBuf::from(trimmed));
    }

    if let Some(rest) = trimmed.strip_prefix("~/") {
        if let Some(home) = dirs::home_dir() {
            return home.join(rest);
        }
    }

    PathBuf::from(trimmed)
}

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

fn resolve_probe_data_dir(data_dir: Option<String>) -> PathBuf {
    let raw_dir = data_dir.unwrap_or_else(default_data_dir);
    let normalized_dir = if raw_dir.trim().is_empty() {
        default_data_dir()
    } else {
        raw_dir
    };
    expand_tilde(&normalized_dir)
}

fn resolve_probe_config_path(
    resolved_data_dir: &Path,
    explicit_config_path: Option<String>,
) -> PathBuf {
    if let Some(raw_path) = explicit_config_path {
        let trimmed = raw_path.trim();
        if !trimmed.is_empty() {
            let expanded = expand_tilde(trimmed);
            if expanded.is_absolute() {
                return expanded;
            }
            return resolved_data_dir.join(expanded);
        }
    }

    let root = project_root();
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(raw_env_path) = std::env::var("MICROCLAW_CONFIG") {
        let trimmed = raw_env_path.trim();
        if !trimmed.is_empty() {
            let expanded = expand_tilde(trimmed);
            if expanded.is_absolute() {
                candidates.push(expanded);
            } else {
                candidates.push(root.join(expanded));
            }
        }
    }

    candidates.push(root.join("drugclaw.config.yaml"));
    candidates.push(root.join("drugclaw.config.yml"));
    candidates.push(resolved_data_dir.join("drugclaw.config.yaml"));
    candidates.push(resolved_data_dir.join("drugclaw.config.yml"));

    for candidate in &candidates {
        if candidate.exists() {
            return candidate.clone();
        }
    }

    candidates
        .into_iter()
        .next()
        .unwrap_or_else(|| resolved_data_dir.join("drugclaw.config.yaml"))
}

fn detect_release_binary(root: &Path) -> bool {
    let primary = root.join("target").join("release").join(if cfg!(windows) {
        "drugclaw.exe"
    } else {
        "drugclaw"
    });
    if primary.exists() {
        return true;
    }

    let fallback = root.join("target").join("release").join(if cfg!(windows) {
        "drugclaw"
    } else {
        "drugclaw.exe"
    });
    fallback.exists()
}

fn release_binary_path(root: &Path) -> PathBuf {
    root.join("target").join("release").join(if cfg!(windows) {
        "drugclaw.exe"
    } else {
        "drugclaw"
    })
}

fn yaml_string(value: Option<&serde_yaml::Value>) -> Option<String> {
    value
        .and_then(|item| item.as_str())
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
}

fn yaml_bool(value: Option<&serde_yaml::Value>) -> Option<bool> {
    value.and_then(|item| item.as_bool())
}

fn yaml_u16(value: Option<&serde_yaml::Value>) -> Option<u16> {
    match value {
        Some(serde_yaml::Value::Number(number)) => {
            number.as_u64().and_then(|num| u16::try_from(num).ok())
        }
        Some(serde_yaml::Value::String(text)) => text.trim().parse::<u16>().ok(),
        _ => None,
    }
}

fn yaml_csv(value: Option<&serde_yaml::Value>) -> String {
    match value {
        Some(serde_yaml::Value::String(text)) => text.trim().to_string(),
        Some(serde_yaml::Value::Sequence(items)) => items
            .iter()
            .filter_map(|item| match item {
                serde_yaml::Value::String(text) => {
                    let trimmed = text.trim();
                    if trimmed.is_empty() {
                        None
                    } else {
                        Some(trimmed.to_string())
                    }
                }
                serde_yaml::Value::Number(number) => Some(number.to_string()),
                _ => None,
            })
            .collect::<Vec<String>>()
            .join(","),
        _ => String::new(),
    }
}

fn resolve_runtime_path(raw_path: &str) -> PathBuf {
    let expanded = expand_tilde(raw_path);
    if expanded.is_absolute() {
        expanded
    } else {
        project_root().join(expanded)
    }
}

fn read_data_dir_from_yaml(parsed: &serde_yaml::Value, fallback_data_dir: &Path) -> PathBuf {
    let Some(raw_data_dir) = yaml_string(parsed.get("data_dir")) else {
        return fallback_data_dir.to_path_buf();
    };
    resolve_runtime_path(&raw_data_dir)
}

fn read_data_dir_from_config(config_path: &Path, fallback_data_dir: &Path) -> PathBuf {
    let content = match fs::read_to_string(config_path) {
        Ok(content) => content,
        Err(_) => return fallback_data_dir.to_path_buf(),
    };
    let parsed: serde_yaml::Value = match serde_yaml::from_str(&content) {
        Ok(parsed) => parsed,
        Err(_) => return fallback_data_dir.to_path_buf(),
    };
    read_data_dir_from_yaml(&parsed, fallback_data_dir)
}

fn config_draft_from_yaml(parsed: &serde_yaml::Value, resolved_data_dir: &Path) -> ConfigDraft {
    let channels = parsed.get("channels");
    let web_channel = channels.and_then(|root| root.get("web"));
    let telegram_channel = channels.and_then(|root| root.get("telegram"));
    let discord_channel = channels.and_then(|root| root.get("discord"));
    let slack_channel = channels.and_then(|root| root.get("slack"));

    ConfigDraft {
        data_dir: yaml_string(parsed.get("data_dir"))
            .unwrap_or_else(|| resolved_data_dir.to_string_lossy().to_string()),
        llm_provider: yaml_string(parsed.get("llm_provider"))
            .unwrap_or_else(|| "openai".to_string()),
        llm_base_url: yaml_string(parsed.get("llm_base_url")).unwrap_or_default(),
        api_key: yaml_string(parsed.get("api_key")).unwrap_or_default(),
        model: yaml_string(parsed.get("model")).unwrap_or_else(|| "gpt-5.2".to_string()),
        web_host: yaml_string(parsed.get("web_host")).unwrap_or_else(|| "127.0.0.1".to_string()),
        web_port: yaml_u16(parsed.get("web_port")).unwrap_or(10961),
        channels: ChannelDraft {
            web_enabled: yaml_bool(web_channel.and_then(|item| item.get("enabled")))
                .unwrap_or(true),
            telegram_enabled: yaml_bool(telegram_channel.and_then(|item| item.get("enabled")))
                .unwrap_or(false),
            telegram_bot_token: yaml_string(
                telegram_channel.and_then(|item| item.get("bot_token")),
            )
            .unwrap_or_default(),
            telegram_bot_username: yaml_string(
                telegram_channel.and_then(|item| item.get("bot_username")),
            )
            .unwrap_or_default(),
            discord_enabled: yaml_bool(discord_channel.and_then(|item| item.get("enabled")))
                .unwrap_or(false),
            discord_bot_token: yaml_string(discord_channel.and_then(|item| item.get("bot_token")))
                .unwrap_or_default(),
            discord_allowed_channels: yaml_csv(
                discord_channel.and_then(|item| item.get("allowed_channels")),
            ),
            slack_enabled: yaml_bool(slack_channel.and_then(|item| item.get("enabled")))
                .unwrap_or(false),
            slack_bot_token: yaml_string(slack_channel.and_then(|item| item.get("bot_token")))
                .unwrap_or_default(),
            slack_app_token: yaml_string(slack_channel.and_then(|item| item.get("app_token")))
                .unwrap_or_default(),
            slack_allowed_channels: yaml_csv(
                slack_channel.and_then(|item| item.get("allowed_channels")),
            ),
        },
    }
}

fn read_working_dir_from_config(config_path: &Path, resolved_data_dir: &Path) -> PathBuf {
    let fallback = resolved_data_dir.join("working_dir");
    let content = match fs::read_to_string(config_path) {
        Ok(content) => content,
        Err(_) => return fallback,
    };
    let parsed: serde_yaml::Value = match serde_yaml::from_str(&content) {
        Ok(parsed) => parsed,
        Err(_) => return fallback,
    };
    let Some(raw_working_dir) = parsed
        .get("working_dir")
        .and_then(|value| value.as_str())
        .map(str::trim)
        .filter(|value| !value.is_empty())
    else {
        return fallback;
    };

    let expanded = expand_tilde(raw_working_dir);
    if expanded.is_absolute() {
        expanded
    } else {
        config_path
            .parent()
            .unwrap_or(resolved_data_dir)
            .join(expanded)
    }
}

fn sqlite_table_exists(db_path: &Path, table_name: &str) -> bool {
    if !db_path.exists() {
        return false;
    }

    let db_path_str = db_path.to_string_lossy().to_string();
    let sql = format!(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='{}' LIMIT 1;",
        table_name.replace('\'', "''")
    );
    let output = match Command::new("sqlite3")
        .args([db_path_str.as_str(), sql.as_str()])
        .stdin(Stdio::null())
        .output()
    {
        Ok(output) => output,
        Err(_) => return false,
    };
    if !output.status.success() {
        return false;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    stdout.lines().any(|line| line.trim() == table_name)
}

fn config_for_yaml(draft: &ConfigDraft) -> FileConfig {
    let raw_data_dir = draft.data_dir.trim();
    let normalized_data_dir = if raw_data_dir.is_empty() {
        "~/.drugclaw"
    } else {
        raw_data_dir
    };

    let work_dir = if normalized_data_dir.ends_with('/') {
        format!("{}working_dir", normalized_data_dir)
    } else {
        format!("{normalized_data_dir}/working_dir")
    };

    let discord_allowed = parse_u64_csv(&draft.channels.discord_allowed_channels);
    let slack_allowed = parse_string_csv(&draft.channels.slack_allowed_channels);

    FileConfig {
        llm_provider: draft.llm_provider.trim().to_lowercase(),
        llm_base_url: if draft.llm_base_url.trim().is_empty() {
            None
        } else {
            Some(draft.llm_base_url.trim().to_string())
        },
        api_key: draft.api_key.trim().to_string(),
        model: draft.model.trim().to_string(),
        data_dir: normalized_data_dir.to_string(),
        working_dir: work_dir,
        channels: FileChannels {
            web: FileWebChannel {
                enabled: draft.channels.web_enabled,
            },
            telegram: FileTelegramChannel {
                enabled: draft.channels.telegram_enabled,
                bot_token: draft.channels.telegram_bot_token.trim().to_string(),
                bot_username: draft.channels.telegram_bot_username.trim().to_string(),
            },
            discord: FileDiscordChannel {
                enabled: draft.channels.discord_enabled,
                bot_token: draft.channels.discord_bot_token.trim().to_string(),
                allowed_channels: if discord_allowed.is_empty() {
                    None
                } else {
                    Some(discord_allowed)
                },
            },
            slack: FileSlackChannel {
                enabled: draft.channels.slack_enabled,
                bot_token: draft.channels.slack_bot_token.trim().to_string(),
                app_token: draft.channels.slack_app_token.trim().to_string(),
                allowed_channels: if slack_allowed.is_empty() {
                    None
                } else {
                    Some(slack_allowed)
                },
            },
        },
        web_host: draft.web_host.trim().to_string(),
        web_port: draft.web_port,
    }
}

fn command_to_string(program: &str, args: &[&str]) -> String {
    let mut cmd = String::from(program);
    for arg in args {
        cmd.push(' ');
        cmd.push_str(arg);
    }
    cmd
}

fn run_command_capture(
    logs: &Arc<Mutex<VecDeque<LogEntry>>>,
    cwd: &Path,
    program: &str,
    args: &[&str],
    envs: &[(&str, &str)],
) -> Result<CommandRunResult, String> {
    let pretty = command_to_string(program, args);
    append_log(logs, "system", format!("$ {pretty}"));

    let mut cmd = Command::new(program);
    cmd.args(args)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    for (k, v) in envs {
        cmd.env(k, v);
    }

    let output = cmd
        .output()
        .map_err(|e| format!("Failed to run `{pretty}`: {e}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    for line in stdout.lines() {
        append_log(logs, "stdout", line.to_string());
    }
    for line in stderr.lines() {
        append_log(logs, "stderr", line.to_string());
    }

    let code = output.status.code().unwrap_or(-1);
    append_log(logs, "system", format!("exit code: {code}"));

    Ok(CommandRunResult {
        command: pretty,
        success: output.status.success(),
        exit_code: code,
        stdout,
        stderr,
    })
}

fn spawn_stream_reader(
    logs: Arc<Mutex<VecDeque<LogEntry>>>,
    stream: &'static str,
    reader: impl std::io::Read + Send + 'static,
) {
    std::thread::spawn(move || {
        let mut buf = BufReader::new(reader);
        let mut line = String::new();
        loop {
            line.clear();
            match buf.read_line(&mut line) {
                Ok(0) => break,
                Ok(_) => append_log(&logs, stream, line.clone()),
                Err(e) => {
                    append_log(&logs, "system", format!("{stream} read error: {e}"));
                    break;
                }
            }
        }
    });
}

fn sync_runtime_status(state: &AppState) -> Result<RuntimeStatus, String> {
    let mut runtime_guard = state
        .runtime
        .lock()
        .map_err(|_| "Runtime state lock poisoned".to_string())?;

    let Some(process) = runtime_guard.as_mut() else {
        return Ok(RuntimeStatus::stopped());
    };

    let child_exit = {
        let mut child_guard = process
            .child
            .lock()
            .map_err(|_| "Runtime child lock poisoned".to_string())?;
        child_guard
            .try_wait()
            .map_err(|e| format!("Failed to query runtime status: {e}"))?
    };

    if let Some(exit_status) = child_exit {
        append_log(
            &state.logs,
            "system",
            format!("runtime exited with status: {exit_status}"),
        );
        *runtime_guard = None;
        return Ok(RuntimeStatus::stopped());
    }

    Ok(RuntimeStatus {
        running: true,
        pid: Some(process.pid),
        uptime_seconds: Some(process.started_instant.elapsed().as_secs()),
        started_at: Some(
            process
                .started_at
                .to_rfc3339_opts(SecondsFormat::Millis, true),
        ),
    })
}

#[tauri::command]
fn default_data_dir() -> String {
    "~/.drugclaw".to_string()
}

#[tauri::command]
fn detect_saved_config(data_dir: Option<String>) -> Result<Option<SaveConfigResult>, String> {
    let fallback_data_dir = resolve_probe_data_dir(data_dir);
    let config_path = resolve_probe_config_path(&fallback_data_dir, None);

    if !config_path.exists() {
        return Ok(None);
    }

    let resolved_data_dir = read_data_dir_from_config(&config_path, &fallback_data_dir);

    Ok(Some(SaveConfigResult {
        config_path: config_path.to_string_lossy().to_string(),
        resolved_data_dir: resolved_data_dir.to_string_lossy().to_string(),
    }))
}

#[tauri::command]
fn load_existing_config(
    data_dir: Option<String>,
    config_path: Option<String>,
) -> Result<LoadedConfigResult, String> {
    let fallback_data_dir = resolve_probe_data_dir(data_dir);
    let detected_config_path = resolve_probe_config_path(&fallback_data_dir, config_path);
    let config_path_str = detected_config_path.to_string_lossy().to_string();

    if !detected_config_path.exists() {
        return Ok(LoadedConfigResult {
            found: false,
            config_path: config_path_str,
            resolved_data_dir: fallback_data_dir.to_string_lossy().to_string(),
            draft: None,
        });
    }

    let content = fs::read_to_string(&detected_config_path).map_err(|e| {
        format!(
            "Failed to read config file {}: {e}",
            detected_config_path.display()
        )
    })?;
    let parsed: serde_yaml::Value = serde_yaml::from_str(&content).map_err(|e| {
        format!(
            "Failed to parse config file {}: {e}",
            detected_config_path.display()
        )
    })?;
    let resolved_data_dir = read_data_dir_from_yaml(&parsed, &fallback_data_dir);
    let draft = config_draft_from_yaml(&parsed, &resolved_data_dir);

    Ok(LoadedConfigResult {
        found: true,
        config_path: config_path_str,
        resolved_data_dir: resolved_data_dir.to_string_lossy().to_string(),
        draft: Some(draft),
    })
}

#[tauri::command]
fn detect_step_progress(
    data_dir: Option<String>,
    config_path: Option<String>,
) -> Result<StepDetectionResult, String> {
    let fallback_data_dir = resolve_probe_data_dir(data_dir);
    let detected_config_path = resolve_probe_config_path(&fallback_data_dir, config_path);
    let has_config = detected_config_path.exists();
    let resolved_data_dir = if has_config {
        read_data_dir_from_config(&detected_config_path, &fallback_data_dir)
    } else {
        fallback_data_dir
    };
    let root = project_root();
    let build_ready = detect_release_binary(&root);
    let runtime_db_path = resolved_data_dir.join("runtime").join("drugclaw.db");
    let runtime_db_exists = runtime_db_path.exists();
    let working_dir = read_working_dir_from_config(&detected_config_path, &resolved_data_dir);
    let init_ready = has_config && (runtime_db_exists || working_dir.is_dir());
    let query_ready = has_config && sqlite_table_exists(&runtime_db_path, "memories");

    Ok(StepDetectionResult {
        has_config,
        config_path: detected_config_path.to_string_lossy().to_string(),
        resolved_data_dir: resolved_data_dir.to_string_lossy().to_string(),
        build_ready,
        init_ready,
        query_ready,
    })
}

#[tauri::command]
fn save_config(state: State<'_, AppState>, draft: ConfigDraft) -> Result<SaveConfigResult, String> {
    let config = config_for_yaml(&draft);
    let yaml =
        serde_yaml::to_string(&config).map_err(|e| format!("Failed to serialize config: {e}"))?;

    let data_dir = expand_tilde(&config.data_dir);
    fs::create_dir_all(data_dir.join("runtime"))
        .map_err(|e| format!("Failed to create runtime directory: {e}"))?;

    let config_path = data_dir.join("drugclaw.config.yaml");
    fs::write(&config_path, yaml).map_err(|e| format!("Failed to save config: {e}"))?;

    append_log(
        &state.logs,
        "system",
        format!("config saved: {}", config_path.display()),
    );

    Ok(SaveConfigResult {
        config_path: config_path.to_string_lossy().to_string(),
        resolved_data_dir: data_dir.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn run_build_step(
    state: State<'_, AppState>,
    config_path: String,
) -> Result<CommandRunResult, String> {
    let root = project_root();
    let config_path_buf = expand_tilde(&config_path);
    let cfg = config_path_buf.to_string_lossy().to_string();
    run_command_capture(
        &state.logs,
        &root,
        "cargo",
        &["build", "--release", "--features", "sqlite-vec"],
        &[("MICROCLAW_CONFIG", cfg.as_str())],
    )
}

#[tauri::command]
fn run_setup_step(
    state: State<'_, AppState>,
    config_path: String,
) -> Result<CommandRunResult, String> {
    let root = project_root();
    let config_path_buf = expand_tilde(&config_path);
    if !config_path_buf.exists() {
        return Err(format!(
            "Config file does not exist: {}",
            config_path_buf.display()
        ));
    }

    let resolved_data_dir =
        read_data_dir_from_config(&config_path_buf, &expand_tilde(&default_data_dir()));
    let working_dir = read_working_dir_from_config(&config_path_buf, &resolved_data_dir);

    fs::create_dir_all(resolved_data_dir.join("runtime"))
        .map_err(|e| format!("Failed to create runtime directory: {e}"))?;
    fs::create_dir_all(&working_dir)
        .map_err(|e| format!("Failed to create working directory: {e}"))?;

    append_log(
        &state.logs,
        "system",
        format!(
            "runtime directory ready: {}",
            resolved_data_dir.join("runtime").display()
        ),
    );
    append_log(
        &state.logs,
        "system",
        format!("working directory ready: {}", working_dir.display()),
    );

    let release_bin = release_binary_path(&root);
    if !release_bin.exists() {
        return Err(format!(
            "Release binary not found: {}. Please run build step first.",
            release_bin.display()
        ));
    }

    let cfg = config_path_buf.to_string_lossy().to_string();
    let bin = release_bin.to_string_lossy().to_string();

    run_command_capture(
        &state.logs,
        &root,
        bin.as_str(),
        &["--config", cfg.as_str(), "doctor"],
        &[],
    )
}

#[tauri::command]
fn start_runtime(state: State<'_, AppState>, config_path: String) -> Result<RuntimeStatus, String> {
    let current_status = sync_runtime_status(&state)?;
    if current_status.running {
        return Ok(current_status);
    }

    let root = project_root();
    let config_path_buf = expand_tilde(&config_path);
    if !config_path_buf.exists() {
        return Err(format!(
            "Config file does not exist: {}",
            config_path_buf.display()
        ));
    }
    let cfg = config_path_buf.to_string_lossy().to_string();
    let release_bin = release_binary_path(&root);
    if !release_bin.exists() {
        return Err(format!(
            "Release binary not found: {}. Please run build step first.",
            release_bin.display()
        ));
    }

    append_log(
        &state.logs,
        "system",
        format!("$ {} --config {} start", release_bin.display(), cfg),
    );

    let mut cmd = Command::new(&release_bin);
    cmd.args(["--config", cfg.as_str(), "start"])
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start runtime process: {e}"))?;

    let pid = child.id();
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    if let Some(stdout) = stdout {
        spawn_stream_reader(state.logs.clone(), "stdout", stdout);
    }
    if let Some(stderr) = stderr {
        spawn_stream_reader(state.logs.clone(), "stderr", stderr);
    }

    let process = RuntimeProcess {
        child: Arc::new(Mutex::new(child)),
        pid,
        started_at: Utc::now(),
        started_instant: Instant::now(),
    };

    let mut runtime_guard = state
        .runtime
        .lock()
        .map_err(|_| "Runtime state lock poisoned".to_string())?;
    *runtime_guard = Some(process);

    append_log(
        &state.logs,
        "system",
        format!("runtime started (pid: {pid})"),
    );
    drop(runtime_guard);

    sync_runtime_status(&state)
}

#[tauri::command]
fn stop_runtime(state: State<'_, AppState>) -> Result<RuntimeStatus, String> {
    let mut runtime_guard = state
        .runtime
        .lock()
        .map_err(|_| "Runtime state lock poisoned".to_string())?;

    if runtime_guard.is_none() {
        return Ok(RuntimeStatus::stopped());
    }

    {
        let process = runtime_guard
            .as_mut()
            .ok_or_else(|| "Runtime state lock poisoned".to_string())?;
        let mut child_guard = process
            .child
            .lock()
            .map_err(|_| "Runtime child lock poisoned".to_string())?;

        child_guard
            .kill()
            .map_err(|e| format!("Failed to stop runtime: {e}"))?;
        let _ = child_guard.wait();
    }
    append_log(&state.logs, "system", "runtime stopped by user".to_string());

    *runtime_guard = None;
    Ok(RuntimeStatus::stopped())
}

#[tauri::command]
fn runtime_status(state: State<'_, AppState>) -> Result<RuntimeStatus, String> {
    sync_runtime_status(&state)
}

#[tauri::command]
fn read_logs(state: State<'_, AppState>, limit: Option<usize>) -> Result<Vec<LogEntry>, String> {
    let limit = limit.unwrap_or(200).min(1000);
    let guard = state
        .logs
        .lock()
        .map_err(|_| "Log lock poisoned".to_string())?;
    let start = guard.len().saturating_sub(limit);
    Ok(guard.iter().skip(start).cloned().collect())
}

#[tauri::command]
fn run_memory_query_step(
    state: State<'_, AppState>,
    data_dir: String,
) -> Result<CommandRunResult, String> {
    let root = project_root();
    let resolved_data_dir = expand_tilde(&data_dir);
    let db_path = resolved_data_dir.join("runtime").join("drugclaw.db");
    let db_path_str = db_path.to_string_lossy().to_string();

    run_command_capture(
        &state.logs,
        &root,
        "sqlite3",
        &[db_path_str.as_str(), MEMORY_SQL],
        &[],
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            default_data_dir,
            detect_saved_config,
            load_existing_config,
            detect_step_progress,
            save_config,
            run_build_step,
            run_setup_step,
            start_runtime,
            stop_runtime,
            runtime_status,
            read_logs,
            run_memory_query_step
        ])
        .run(tauri::generate_context!())
        .expect("error while running DrugClaw Desktop");
}

fn main() {
    run();
}

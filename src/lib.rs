pub mod agent_engine;
pub mod channels;
pub mod chat_commands;
pub mod clawhub;
pub mod codex_auth;
pub mod config;
pub mod doctor;
pub mod embedding;
pub mod gateway;
pub mod hooks;
pub mod http_client;
pub mod llm;
pub mod mcp;
pub mod memory_backend;
pub mod otlp;
pub mod plugins;
pub(crate) mod run_control;
pub mod runtime;
pub mod scheduler;
pub mod setup;
pub mod setup_def;
pub mod skills;
pub mod tools;
pub mod web;

pub use channels::discord;
pub use channels::telegram;
pub use drugclaw_app::builtin_skills;
pub use drugclaw_app::logging;
pub use drugclaw_app::transcribe;
pub use drugclaw_channels::channel;
pub use drugclaw_channels::channel_adapter;
pub use drugclaw_core::error;
pub use drugclaw_core::llm_types;
pub use drugclaw_core::text;
pub use drugclaw_storage::db;
pub use drugclaw_storage::memory;
pub use drugclaw_storage::memory_quality;
pub use drugclaw_tools::sandbox;

#[cfg(test)]
pub mod test_support {
    use std::io::ErrorKind;
    use std::net::TcpListener;
    use std::sync::{Mutex, MutexGuard, OnceLock};

    pub fn env_lock() -> MutexGuard<'static, ()> {
        static ENV_LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        match ENV_LOCK.get_or_init(|| Mutex::new(())).lock() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        }
    }

    pub fn bind_test_listener() -> Option<TcpListener> {
        match TcpListener::bind("127.0.0.1:0") {
            Ok(listener) => Some(listener),
            Err(err)
                if matches!(
                    err.kind(),
                    ErrorKind::PermissionDenied | ErrorKind::AddrNotAvailable
                ) =>
            {
                None
            }
            Err(err) => panic!("failed to bind loopback test listener: {err}"),
        }
    }
}

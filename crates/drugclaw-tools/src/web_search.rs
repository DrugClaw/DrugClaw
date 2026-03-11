use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use crate::web_html::extract_ddg_results;

fn http_client(timeout_secs: u64) -> reqwest::Client {
    static CLIENTS: OnceLock<Mutex<HashMap<u64, reqwest::Client>>> = OnceLock::new();
    let cache = CLIENTS.get_or_init(|| Mutex::new(HashMap::new()));
    let mut cache = cache.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(client) = cache.get(&timeout_secs) {
        return client.clone();
    }
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(timeout_secs))
        .redirect(reqwest::redirect::Policy::limited(5))
        .user_agent("DrugClaw/1.0")
        .build()
        .expect("failed to build HTTP client");
    cache.insert(timeout_secs, client.clone());
    client
}

pub async fn search_ddg_with_timeout(query: &str, timeout_secs: u64) -> Result<String, String> {
    let encoded = urlencoding::encode(query);
    let url = format!("https://html.duckduckgo.com/html/?q={encoded}");
    let client = http_client(timeout_secs.max(1));

    let resp = client.get(&url).send().await.map_err(|e| e.to_string())?;

    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }

    let body = resp.text().await.map_err(|e| e.to_string())?;
    let items = extract_ddg_results(&body, 8);

    let mut output = String::new();
    for (i, item) in items.iter().enumerate() {
        output.push_str(&format!(
            "{}. {}\n   {}\n   {}\n\n",
            i + 1,
            item.title,
            item.url,
            item.snippet
        ));
    }

    Ok(output)
}

pub async fn search_ddg(query: &str) -> Result<String, String> {
    search_ddg_with_timeout(query, 15).await
}

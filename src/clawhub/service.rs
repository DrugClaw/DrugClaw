use std::path::Path;

use async_trait::async_trait;
use drugclaw_clawhub::client::ClawHubClient;
use drugclaw_clawhub::install::{install_skill, InstallOptions, InstallResult};
use drugclaw_clawhub::lockfile::read_lockfile;
use drugclaw_clawhub::types::{LockFile, SearchResult, SkillMeta};

use crate::config::Config;
use crate::error::DrugClawError;

#[async_trait]
pub trait ClawHubGateway: Send + Sync {
    async fn search(
        &self,
        query: &str,
        limit: usize,
        sort: &str,
    ) -> Result<Vec<SearchResult>, DrugClawError>;
    async fn get_skill(&self, slug: &str) -> Result<SkillMeta, DrugClawError>;
    async fn install(
        &self,
        slug: &str,
        version: Option<&str>,
        skills_dir: &Path,
        lockfile_path: &Path,
        options: &InstallOptions,
    ) -> Result<InstallResult, DrugClawError>;
    fn read_lockfile(&self, path: &Path) -> Result<LockFile, DrugClawError>;
}

pub struct RegistryClawHubGateway {
    client: ClawHubClient,
}

impl RegistryClawHubGateway {
    pub fn from_config(config: &Config) -> Self {
        let client = ClawHubClient::new(&config.clawhub.registry, config.clawhub.token.clone());
        Self { client }
    }
}

#[async_trait]
impl ClawHubGateway for RegistryClawHubGateway {
    async fn search(
        &self,
        query: &str,
        limit: usize,
        sort: &str,
    ) -> Result<Vec<SearchResult>, DrugClawError> {
        self.client.search(query, limit, sort).await
    }

    async fn get_skill(&self, slug: &str) -> Result<SkillMeta, DrugClawError> {
        self.client.get_skill(slug).await
    }

    async fn install(
        &self,
        slug: &str,
        version: Option<&str>,
        skills_dir: &Path,
        lockfile_path: &Path,
        options: &InstallOptions,
    ) -> Result<InstallResult, DrugClawError> {
        install_skill(
            &self.client,
            slug,
            version,
            skills_dir,
            lockfile_path,
            options,
        )
        .await
    }

    fn read_lockfile(&self, path: &Path) -> Result<LockFile, DrugClawError> {
        read_lockfile(path)
    }
}

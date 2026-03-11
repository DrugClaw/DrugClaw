# DrugClaw Tauri Client

黑绿主题的 DrugClaw 桌面端，提供步骤化配置和运行面板：

1. `cargo build --release --features sqlite-vec`
2. 图形化配置（默认 `~/.drugclaw`，覆盖 `setup`）
3. `cargo run --features sqlite-vec -- start`
4. `sqlite3 <data_dir>/runtime/drugclaw.db "SELECT ... LIMIT 20;"`

## 启动

```bash
cd drugclaw-tauri
npm install
npm run tauri dev
```

## 说明

- 配置文件保存到：`<data_dir>/drugclaw.config.yaml`
- 运行命令时会自动传递 `--config <config_path>` 与 `MICROCLAW_CONFIG`
- 日志面板会持续刷新并展示运行状态、运行时间（uptime）和输出

import { Field } from '../components/Field'
import { Toggle } from '../components/Toggle'
import type { ConfigDraft, RuntimeStatus, ProviderPresetOption } from '../types'

type SetupViewProps = {
  draft: ConfigDraft
  setDraft: (fn: (prev: ConfigDraft) => ConfigDraft) => void
  configPath: string
  buildReady: boolean
  initReady: boolean
  completedSteps: number
  guideProgress: number
  statusText: string
  busyAction: string
  providerOptions: ProviderPresetOption[]
  modelOptions: string[]
  providerBaseUrlPlaceholder: string
  runtime: RuntimeStatus
  saveConfig: () => void
  runBuild: () => void
  runSetup: () => void
}

export function SetupView({
  draft,
  setDraft,
  configPath,
  buildReady,
  initReady,
  completedSteps,
  guideProgress,
  statusText,
  busyAction,
  providerOptions,
  modelOptions,
  providerBaseUrlPlaceholder,
  runtime,
  saveConfig,
  runBuild,
  runSetup,
}: SetupViewProps) {
  return (
    <section className="flex flex-col gap-5">
      {/* Progress Card */}
      <article className="border border-zinc-700/50 rounded-2xl p-5 bg-gradient-to-br from-zinc-800/50 via-zinc-900/60 to-zinc-950/70 backdrop-blur shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-zinc-100">快速开始</h2>
          <span className="text-xs border border-emerald-400/50 rounded-full px-3 py-1 bg-emerald-500/15 text-emerald-200 font-medium">
            {completedSteps}/4 步骤
          </span>
        </div>
        <div className="w-full h-3 rounded-full bg-zinc-800/80 border border-zinc-700/60 overflow-hidden mb-4">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 via-emerald-400 to-green-500 transition-all duration-500 shadow-lg shadow-emerald-500/50"
            style={{ width: `${guideProgress}%` }}
          />
        </div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {[
            { done: configPath, label: '配置 AI 模型' },
            { done: buildReady, label: '准备环境' },
            { done: initReady, label: '初始化系统' },
            { done: runtime.running, label: '启动助手' },
          ].map((item, idx) => (
            <div
              key={idx}
              className={`border rounded-xl p-3 flex items-center gap-2.5 transition-all ${
                item.done
                  ? 'border-emerald-400/50 bg-gradient-to-br from-emerald-500/15 to-green-500/10 shadow-lg shadow-emerald-500/10'
                  : 'border-zinc-700/60 bg-zinc-800/40'
              }`}
            >
              <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border ${
                item.done
                  ? 'border-emerald-400 text-emerald-100 bg-emerald-500/30'
                  : 'border-zinc-600 text-zinc-400 bg-zinc-800/80'
              }`}>
                {idx + 1}
              </span>
              <p className="text-sm text-zinc-200">{item.label}</p>
            </div>
          ))}
        </div>
        <p className="text-sm text-zinc-300">{statusText}</p>
        <p className="text-xs text-zinc-400 mt-1.5">
          首次保存并初始化后，通常只需在模型或渠道发生变化时更新配置。
        </p>
      </article>

      {/* Config Card */}
      <article className="border border-zinc-700/50 rounded-2xl p-5 bg-gradient-to-br from-zinc-800/50 via-zinc-900/60 to-zinc-950/70 backdrop-blur shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-zinc-100">AI 模型配置</h2>
          <span className="text-xs border border-zinc-600/50 rounded-full px-3 py-1 bg-zinc-700/30 text-zinc-300">
            数据目录: {draft.dataDir || '~/.drugclaw'}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <Field label="数据存储位置" hint="建议为不同研究项目创建独立目录">
            <input
              className="w-full border border-zinc-600/60 rounded-lg px-3 py-2 bg-zinc-800/60 text-zinc-100 text-sm focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/30 transition-all"
              value={draft.dataDir}
              onChange={(e) => setDraft((prev) => ({ ...prev, dataDir: e.target.value }))}
              placeholder="~/.drugclaw"
            />
          </Field>
          <Field label="AI 服务商" hint="从常用服务商中选择">
            <select
              className="w-full border border-zinc-600/60 rounded-lg px-3 py-2 bg-zinc-800/60 text-zinc-100 text-sm focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/30 transition-all cursor-pointer hover:border-zinc-500"
              value={draft.llmProvider.trim().toLowerCase()}
              onChange={(e) => {
                const nextProvider = e.target.value.trim().toLowerCase()
                const preset = providerOptions.find(p => p.value === nextProvider)
                setDraft((prev) => ({
                  ...prev,
                  llmProvider: nextProvider,
                  model: preset?.models[0] || prev.model,
                  llmBaseUrl: preset?.baseUrl || prev.llmBaseUrl,
                }))
              }}
            >
              {providerOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </Field>
          <Field label="模型版本" hint="根据服务商自动推荐模型列表">
            <select
              className="w-full border border-zinc-600/60 rounded-lg px-3 py-2 bg-zinc-800/60 text-zinc-100 text-sm focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/30 transition-all cursor-pointer hover:border-zinc-500"
              value={draft.model}
              onChange={(e) => setDraft((prev) => ({ ...prev, model: e.target.value }))}
            >
              {modelOptions.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </Field>
          <Field label="Base URL" hint="可覆盖默认地址，留空将使用服务商默认值">
            <input
              className="w-full border border-zinc-600/60 rounded-lg px-3 py-2 bg-zinc-800/60 text-zinc-100 text-sm focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/30 transition-all"
              value={draft.llmBaseUrl}
              onChange={(e) => setDraft((prev) => ({ ...prev, llmBaseUrl: e.target.value }))}
              placeholder={providerBaseUrlPlaceholder}
            />
          </Field>
          <Field label="API 密钥">
            <input
              type="password"
              className="w-full border border-zinc-600/60 rounded-lg px-3 py-2 bg-zinc-800/60 text-zinc-100 text-sm focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/30 transition-all"
              value={draft.apiKey}
              onChange={(e) => setDraft((prev) => ({ ...prev, apiKey: e.target.value }))}
              placeholder="输入 API Key"
            />
          </Field>
        </div>

        <details className="border border-zinc-700/60 rounded-xl p-3 bg-zinc-800/40 mb-4">
          <summary className="cursor-pointer text-xs text-zinc-300 font-medium">高级网络设置</summary>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <Field label="本地地址">
              <input
                className="w-full border border-zinc-600/60 rounded-lg px-3 py-2 bg-zinc-800/60 text-zinc-100 text-sm focus:outline-none focus:border-emerald-400 transition-all"
                value={draft.webHost}
                onChange={(e) => setDraft((prev) => ({ ...prev, webHost: e.target.value }))}
                placeholder="127.0.0.1"
              />
            </Field>
            <Field label="端口">
              <input
                type="number"
                className="w-full border border-zinc-600/60 rounded-lg px-3 py-2 bg-zinc-800/60 text-zinc-100 text-sm focus:outline-none focus:border-emerald-400 transition-all"
                value={draft.webPort}
                onChange={(e) => setDraft((prev) => ({ ...prev, webPort: Number(e.target.value || 10961) }))}
                min={1}
                max={65535}
              />
            </Field>
          </div>
        </details>

        <h3 className="text-sm font-medium text-zinc-200 mb-3">接入方式</h3>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3">
            <Toggle
              checked={draft.channels.webEnabled}
              onChange={(next) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, webEnabled: next } }))}
              label="网页界面"
            />
          </div>
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3 flex flex-col gap-2">
            <Toggle
              checked={draft.channels.telegramEnabled}
              onChange={(next) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, telegramEnabled: next } }))}
              label="Telegram"
            />
            {draft.channels.telegramEnabled && (
              <>
                <input
                  className="w-full border border-zinc-600/60 rounded-lg px-2 py-1.5 bg-zinc-900/60 text-zinc-100 text-xs focus:outline-none focus:border-emerald-400"
                  value={draft.channels.telegramBotToken}
                  onChange={(e) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, telegramBotToken: e.target.value } }))}
                  placeholder="Bot Token"
                />
                <input
                  className="w-full border border-zinc-600/60 rounded-lg px-2 py-1.5 bg-zinc-900/60 text-zinc-100 text-xs focus:outline-none focus:border-emerald-400"
                  value={draft.channels.telegramBotUsername}
                  onChange={(e) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, telegramBotUsername: e.target.value } }))}
                  placeholder="Bot 用户名"
                />
              </>
            )}
          </div>
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3 flex flex-col gap-2">
            <Toggle
              checked={draft.channels.discordEnabled}
              onChange={(next) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, discordEnabled: next } }))}
              label="Discord"
            />
            {draft.channels.discordEnabled && (
              <>
                <input
                  className="w-full border border-zinc-600/60 rounded-lg px-2 py-1.5 bg-zinc-900/60 text-zinc-100 text-xs focus:outline-none focus:border-emerald-400"
                  value={draft.channels.discordBotToken}
                  onChange={(e) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, discordBotToken: e.target.value } }))}
                  placeholder="Bot Token"
                />
                <input
                  className="w-full border border-zinc-600/60 rounded-lg px-2 py-1.5 bg-zinc-900/60 text-zinc-100 text-xs focus:outline-none focus:border-emerald-400"
                  value={draft.channels.discordAllowedChannels}
                  onChange={(e) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, discordAllowedChannels: e.target.value } }))}
                  placeholder="频道 ID，逗号分隔"
                />
              </>
            )}
          </div>
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3 flex flex-col gap-2">
            <Toggle
              checked={draft.channels.slackEnabled}
              onChange={(next) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, slackEnabled: next } }))}
              label="Slack"
            />
            {draft.channels.slackEnabled && (
              <>
                <input
                  className="w-full border border-zinc-600/60 rounded-lg px-2 py-1.5 bg-zinc-900/60 text-zinc-100 text-xs focus:outline-none focus:border-emerald-400"
                  value={draft.channels.slackBotToken}
                  onChange={(e) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, slackBotToken: e.target.value } }))}
                  placeholder="Bot Token"
                />
                <input
                  className="w-full border border-zinc-600/60 rounded-lg px-2 py-1.5 bg-zinc-900/60 text-zinc-100 text-xs focus:outline-none focus:border-emerald-400"
                  value={draft.channels.slackAppToken}
                  onChange={(e) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, slackAppToken: e.target.value } }))}
                  placeholder="App Token"
                />
                <input
                  className="w-full border border-zinc-600/60 rounded-lg px-2 py-1.5 bg-zinc-900/60 text-zinc-100 text-xs focus:outline-none focus:border-emerald-400"
                  value={draft.channels.slackAllowedChannels}
                  onChange={(e) => setDraft((prev) => ({ ...prev, channels: { ...prev.channels, slackAllowedChannels: e.target.value } }))}
                  placeholder="频道名称，逗号分隔"
                />
              </>
            )}
          </div>
        </div>

        <div className="flex gap-2 flex-wrap">
          <button
            className="border border-emerald-400/60 rounded-xl bg-gradient-to-br from-emerald-500/40 to-green-500/40 text-white px-4 py-2 text-sm font-semibold hover:from-emerald-500/50 hover:to-green-500/50 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-emerald-500/20"
            disabled={busyAction === 'save'}
            onClick={saveConfig}
          >
            {busyAction === 'save' ? '保存中...' : '保存配置'}
          </button>
          <button
            className="border border-zinc-600 rounded-xl bg-zinc-800/80 text-zinc-200 px-4 py-2 text-sm font-semibold hover:border-emerald-400/60 hover:text-emerald-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            disabled={busyAction === 'build' || !configPath}
            onClick={runBuild}
          >
            {busyAction === 'build' ? '准备中...' : '准备环境'}
          </button>
          <button
            className="border border-zinc-600 rounded-xl bg-zinc-800/80 text-zinc-200 px-4 py-2 text-sm font-semibold hover:border-emerald-400/60 hover:text-emerald-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            disabled={busyAction === 'setup' || !configPath || !buildReady}
            onClick={runSetup}
          >
            {busyAction === 'setup' ? '初始化中...' : '初始化'}
          </button>
        </div>

        {configPath && (
          <p className="text-xs text-zinc-400 mt-3">
            配置文件: <code className="text-emerald-300">{configPath}</code>
          </p>
        )}
      </article>
    </section>
  )
}

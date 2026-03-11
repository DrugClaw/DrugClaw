import { useEffect, useMemo, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'
import appIcon from '../src-tauri/icons/icon.png'
import { StatusBadge } from './components/StatusBadge'
import { PROVIDER_PRESETS } from './config/providers'
import { SetupView } from './views/SetupView'
import { OperationsView } from './views/OperationsView'
import type {
  ConfigDraft,
  RuntimeStatus,
  LogEntry,
  LogFilter,
  WorkspaceView,
  SaveConfigResult,
  LoadedConfigResult,
  CommandRunResult,
  StepDetectionResult,
} from './types'

type PersistedUiState = {
  configPath: string
  resolvedDataDir: string
  workspaceView: WorkspaceView
  dataPanelExpanded: boolean
  logsPanelExpanded: boolean
}

const UI_STATE_STORAGE_KEY = 'drugclaw.desktop.ui.v1'

const PROVIDER_MODEL_MAP = PROVIDER_PRESETS.reduce<Record<string, string[]>>((acc, item) => {
  acc[item.value] = item.models
  return acc
}, {})

const PROVIDER_BASE_URL_MAP = PROVIDER_PRESETS.reduce<Record<string, string>>((acc, item) => {
  acc[item.value] = item.baseUrl
  return acc
}, {})

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

function isCargoNoiseLine(line: string): boolean {
  const normalized = line.trim()
  if (!normalized) return true

  return (
    /^warning:\s*`.*\/\.cargo\/config`\s*is deprecated in favor of `config\.toml`$/i.test(normalized) ||
    /^\|$/.test(normalized) ||
    /^= help:/i.test(normalized) ||
    /^Compiling\b/.test(normalized) ||
    /^Building \[/.test(normalized) ||
    /^Finished `.*` profile/.test(normalized) ||
    /^Running `.*`$/.test(normalized) ||
    /^Blocking waiting for file lock on artifact directory$/.test(normalized)
  )
}

function summarizeCommandFailure(result: CommandRunResult): string {
  const lines = `${result.stderr}\n${result.stdout}`
    .split('\n')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)

  const strongMatch = lines.find((line) => {
    if (isCargoNoiseLine(line)) return false
    const lower = line.toLowerCase()
    return (
      lower.includes('error:') ||
      lower.includes('failed') ||
      lower.includes('could not') ||
      lower.includes('panic') ||
      lower.includes('caused by')
    )
  })
  if (strongMatch) return strongMatch

  const weakMatch = lines.find((line) => !isCargoNoiseLine(line))
  if (weakMatch) return weakMatch

  return `退出码 ${result.exitCode}`
}

function formatUptime(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function formatStartedAt(timestamp?: string | null): string {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp
  return date.toLocaleString('zh-CN', { hour12: false })
}

function parseMemoryRows(stdout: string): string[][] {
  return stdout
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => line.split('|').map((cell) => cell.trim()))
}

export function App() {
  const [draft, setDraft] = useState<ConfigDraft>({
    dataDir: '~/.drugclaw',
    llmProvider: 'openai',
    apiKey: '',
    model: 'gpt-5.2',
    llmBaseUrl: 'https://api.openai.com/v1',
    webHost: '127.0.0.1',
    webPort: 10961,
    channels: {
      webEnabled: true,
      telegramEnabled: false,
      telegramBotToken: '',
      telegramBotUsername: '',
      discordEnabled: false,
      discordBotToken: '',
      discordAllowedChannels: '',
      slackEnabled: false,
      slackBotToken: '',
      slackAppToken: '',
      slackAllowedChannels: '',
    },
  })

  const [configPath, setConfigPath] = useState<string>('')
  const [resolvedDataDir, setResolvedDataDir] = useState<string>('')
  const [runtime, setRuntime] = useState<RuntimeStatus>({ running: false })
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [memoryRows, setMemoryRows] = useState<string[][]>([])
  const [errorText, setErrorText] = useState<string>('')
  const [statusText, setStatusText] = useState<string>('等待配置')
  const [busyAction, setBusyAction] = useState<string>('')
  const [buildReady, setBuildReady] = useState<boolean>(false)
  const [initReady, setInitReady] = useState<boolean>(false)
  const [queryReady, setQueryReady] = useState<boolean>(false)
  const [uptimeSeries, setUptimeSeries] = useState<number[]>([])
  const [logFilter, setLogFilter] = useState<LogFilter>('all')
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>('setup')
  const [dataPanelExpanded, setDataPanelExpanded] = useState<boolean>(false)
  const [logsPanelExpanded, setLogsPanelExpanded] = useState<boolean>(true)
  const [uiHydrated, setUiHydrated] = useState<boolean>(false)

  const filteredLogs = useMemo(() => {
    if (logFilter === 'all') return logs
    return logs.filter((entry) => entry.stream === logFilter)
  }, [logs, logFilter])

  const streamStats = useMemo(() => {
    const base = [
      { key: 'system' as const, label: '系统事件', count: 0, ratio: 0 },
      { key: 'stdout' as const, label: '运行输出', count: 0, ratio: 0 },
      { key: 'stderr' as const, label: '异常输出', count: 0, ratio: 0 },
    ]

    const total = Math.max(1, logs.length)
    const counter = new Map<string, number>()
    for (const log of logs) {
      counter.set(log.stream, (counter.get(log.stream) || 0) + 1)
    }

    for (const item of base) {
      item.count = counter.get(item.key) || 0
      item.ratio = item.count / total
    }
    return base
  }, [logs])

  const activityBins = useMemo(() => {
    const now = Date.now()
    const bins = new Array(12).fill(0)

    for (const log of logs) {
      const ts = Date.parse(log.timestamp)
      if (Number.isNaN(ts)) continue
      const deltaMinutes = Math.floor((now - ts) / 60000)
      if (deltaMinutes < 0 || deltaMinutes >= 36) continue
      const slot = 11 - Math.floor(deltaMinutes / 3)
      bins[Math.max(0, Math.min(11, slot))] += 1
    }

    return bins
  }, [logs])

  const completedSteps = useMemo(() => {
    const flags = [
      Boolean(configPath),
      buildReady,
      initReady,
      runtime.running,
    ]
    return flags.filter(Boolean).length
  }, [buildReady, configPath, initReady, runtime.running])

  const guideProgress = Math.round((completedSteps / 4) * 100)

  const providerOptions = useMemo(() => {
    const normalizedProvider = draft.llmProvider.trim().toLowerCase()
    if (!normalizedProvider) return PROVIDER_PRESETS
    if (PROVIDER_MODEL_MAP[normalizedProvider]) return PROVIDER_PRESETS
    return [
      ...PROVIDER_PRESETS,
      {
        value: normalizedProvider,
        label: `${normalizedProvider} (当前配置)`,
        models: draft.model ? [draft.model] : [],
        baseUrl: draft.llmBaseUrl,
      },
    ]
  }, [draft.llmBaseUrl, draft.llmProvider, draft.model])

  const modelOptions = useMemo(() => {
    const normalizedProvider = draft.llmProvider.trim().toLowerCase()
    const suggested = PROVIDER_MODEL_MAP[normalizedProvider] ?? []
    const currentModel = draft.model.trim()
    if (!currentModel) return suggested
    if (suggested.includes(currentModel)) return suggested
    return [currentModel, ...suggested]
  }, [draft.llmProvider, draft.model])

  const providerBaseUrlPlaceholder = useMemo(() => {
    const normalizedProvider = draft.llmProvider.trim().toLowerCase()
    return PROVIDER_BASE_URL_MAP[normalizedProvider] || '留空使用服务商默认地址'
  }, [draft.llmProvider])

  useEffect(() => {
    const uptime = runtime.uptimeSeconds
    if (!runtime.running || uptime === undefined || uptime === null) {
      return
    }

    setUptimeSeries((prev) => {
      if (prev.length > 0 && prev[prev.length - 1] === uptime) {
        return prev
      }
      const next = [...prev, uptime]
      return next.slice(-60)
    })
  }, [runtime.running, runtime.uptimeSeconds])

  useEffect(() => {
    if (runtime.running && workspaceView === 'setup') {
      setWorkspaceView('operations')
    }
  }, [runtime.running, workspaceView])

  async function refreshStatusAndLogs(): Promise<void> {
    try {
      const [nextStatus, nextLogs] = await Promise.all([
        invoke<RuntimeStatus>('runtime_status'),
        invoke<LogEntry[]>('read_logs', { limit: 400 }),
      ])
      setRuntime(nextStatus)
      setLogs(nextLogs)
    } catch {
      // Keep current state
    }
  }

  async function detectStepProgress(input?: { dataDir?: string; configPath?: string }): Promise<void> {
    try {
      const detected = await invoke<StepDetectionResult>('detect_step_progress', {
        dataDir: input?.dataDir ?? null,
        configPath: input?.configPath ?? null,
      })
      setBuildReady(detected.buildReady)
      setInitReady(detected.initReady)
      setQueryReady(detected.queryReady)
      setResolvedDataDir(detected.resolvedDataDir)

      if (detected.hasConfig) {
        setConfigPath(detected.configPath)
        setStatusText((prev) => (prev === '等待配置' ? '已检测到历史环境，步骤状态已同步。' : prev))
      } else {
        setConfigPath('')
      }
    } catch {
      // Keep fallback.
    }
  }

  useEffect(() => {
    let restoredDataDir: string | null = null
    let restoredConfigPath: string | null = null

    try {
      const raw = window.localStorage.getItem(UI_STATE_STORAGE_KEY)
      if (raw) {
        const restored = JSON.parse(raw) as Partial<PersistedUiState>
        if (typeof restored.configPath === 'string') {
          restoredConfigPath = restored.configPath
          setConfigPath(restored.configPath)
        }
        if (typeof restored.resolvedDataDir === 'string') {
          setResolvedDataDir(restored.resolvedDataDir)
          restoredDataDir = restored.resolvedDataDir
        }
        if (restored.workspaceView === 'setup' || restored.workspaceView === 'operations') {
          setWorkspaceView(restored.workspaceView)
        }
        if (typeof restored.dataPanelExpanded === 'boolean') {
          setDataPanelExpanded(restored.dataPanelExpanded)
        }
        if (typeof restored.logsPanelExpanded === 'boolean') {
          setLogsPanelExpanded(restored.logsPanelExpanded)
        }
      }
    } catch {
      // Ignore invalid local state.
    }

    void (async () => {
      let probeDataDir = restoredDataDir
      try {
        if (!probeDataDir) {
          const defaultDir = await invoke<string>('default_data_dir')
          probeDataDir = defaultDir
        }

        let effectiveDataDir = probeDataDir || undefined
        let effectiveConfigPath = restoredConfigPath || undefined
        const loaded = await invoke<LoadedConfigResult>('load_existing_config', {
          dataDir: probeDataDir || null,
          configPath: restoredConfigPath || null,
        })
        if (loaded.found && loaded.draft) {
          setDraft(loaded.draft)
          setConfigPath(loaded.configPath)
          setResolvedDataDir(loaded.resolvedDataDir)
          setStatusText('已自动读取现有配置。')
          effectiveDataDir = loaded.resolvedDataDir
          effectiveConfigPath = loaded.configPath
        } else if (probeDataDir) {
          setDraft((prev) => ({ ...prev, dataDir: probeDataDir || prev.dataDir }))
        }

        await detectStepProgress({
          dataDir: effectiveDataDir,
          configPath: effectiveConfigPath,
        })
      } catch {
        // Keep fallback.
      } finally {
        await refreshStatusAndLogs()
        setUiHydrated(true)
      }
    })()

    const timer = window.setInterval(() => {
      void refreshStatusAndLogs()
    }, 1200)

    return () => {
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (!uiHydrated) return
    try {
      const state: PersistedUiState = {
        configPath,
        resolvedDataDir,
        workspaceView,
        dataPanelExpanded,
        logsPanelExpanded,
      }
      window.localStorage.setItem(UI_STATE_STORAGE_KEY, JSON.stringify(state))
    } catch {
      // Ignore localStorage failures.
    }
  }, [
    configPath,
    dataPanelExpanded,
    logsPanelExpanded,
    resolvedDataDir,
    uiHydrated,
    workspaceView,
  ])

  async function saveConfig(): Promise<void> {
    setBusyAction('save')
    setErrorText('')
    try {
      const result = await invoke<SaveConfigResult>('save_config', { draft })
      setConfigPath(result.configPath)
      setResolvedDataDir(result.resolvedDataDir)
      setStatusText('配置已保存')
      await refreshStatusAndLogs()
      await detectStepProgress({
        dataDir: result.resolvedDataDir,
        configPath: result.configPath,
      })
    } catch (error) {
      setErrorText(toErrorMessage(error))
    } finally {
      setBusyAction('')
    }
  }

  async function runBuild(): Promise<void> {
    if (!configPath) {
      setErrorText('请先保存配置')
      return
    }

    setBusyAction('build')
    setErrorText('')
    try {
      const result = await invoke<CommandRunResult>('run_build_step', { configPath })
      if (result.success) {
        setBuildReady(true)
        setStatusText('环境准备完成')
      } else {
        setStatusText(`环境准备失败：${summarizeCommandFailure(result)}`)
      }
      await refreshStatusAndLogs()
      await detectStepProgress({
        dataDir: resolvedDataDir || draft.dataDir,
        configPath,
      })
    } catch (error) {
      setErrorText(toErrorMessage(error))
    } finally {
      setBusyAction('')
    }
  }

  async function runSetup(): Promise<void> {
    if (!configPath) {
      setErrorText('请先保存配置')
      return
    }

    setBusyAction('setup')
    setErrorText('')
    try {
      const result = await invoke<CommandRunResult>('run_setup_step', { configPath })
      if (result.success) {
        setInitReady(true)
        setStatusText('初始化完成')
      } else {
        setStatusText(`初始化失败：${summarizeCommandFailure(result)}`)
      }
      await refreshStatusAndLogs()
      await detectStepProgress({
        dataDir: resolvedDataDir || draft.dataDir,
        configPath,
      })
    } catch (error) {
      setErrorText(toErrorMessage(error))
    } finally {
      setBusyAction('')
    }
  }

  async function startRuntime(): Promise<void> {
    if (!configPath) {
      setErrorText('请先保存配置')
      return
    }

    setBusyAction('start')
    setErrorText('')
    try {
      const status = await invoke<RuntimeStatus>('start_runtime', { configPath })
      setRuntime(status)
      setStatusText('DrugClaw 正在运行')
      await refreshStatusAndLogs()
      await detectStepProgress({
        dataDir: resolvedDataDir || draft.dataDir,
        configPath,
      })
    } catch (error) {
      setErrorText(toErrorMessage(error))
    } finally {
      setBusyAction('')
    }
  }

  async function stopRuntime(): Promise<void> {
    setBusyAction('stop')
    setErrorText('')
    try {
      const status = await invoke<RuntimeStatus>('stop_runtime')
      setRuntime(status)
      setStatusText('已停止')
      await refreshStatusAndLogs()
      await detectStepProgress({
        dataDir: resolvedDataDir || draft.dataDir,
        configPath: configPath || undefined,
      })
    } catch (error) {
      setErrorText(toErrorMessage(error))
    } finally {
      setBusyAction('')
    }
  }

  async function runMemoryQuery(): Promise<void> {
    setBusyAction('query')
    setErrorText('')
    const targetDir = resolvedDataDir || draft.dataDir

    try {
      const result = await invoke<CommandRunResult>('run_memory_query_step', {
        dataDir: targetDir,
      })

      if (result.success) {
        setMemoryRows(parseMemoryRows(result.stdout))
        setQueryReady(true)
        setStatusText('数据已更新')
      } else {
        setStatusText(`数据刷新失败：${summarizeCommandFailure(result)}`)
      }
      await refreshStatusAndLogs()
      await detectStepProgress({
        dataDir: targetDir,
        configPath: configPath || undefined,
      })
    } catch (error) {
      setErrorText(toErrorMessage(error))
    } finally {
      setBusyAction('')
    }
  }

  return (
    <div className="min-h-screen max-w-7xl mx-auto w-full p-6 flex flex-col gap-5 text-zinc-100 selection:bg-emerald-400/30">
      {/* Header */}
      <header className="flex justify-between items-start gap-4 p-6 border border-zinc-700/50 rounded-2xl bg-gradient-to-br from-zinc-900/80 via-black/85 to-zinc-950/90 backdrop-blur-xl shadow-2xl shadow-emerald-500/10">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-xl border border-emerald-400/40 bg-zinc-900/80 p-1.5 shadow-lg shadow-emerald-500/20">
            <img
              src={appIcon}
              alt="DrugClaw"
              className="w-full h-full object-cover rounded-lg"
            />
          </div>
          <div>
            <h1 className="text-2xl font-bold mb-1 bg-gradient-to-r from-emerald-300 to-green-300 bg-clip-text text-transparent">
              DrugClaw 研究助手
            </h1>
            <p className="text-zinc-400 text-sm">AI 驱动的药物发现加速平台</p>
          </div>
        </div>
        <StatusBadge
          running={runtime.running}
          progress={guideProgress}
          canStart={Boolean(configPath) && buildReady}
          busyAction={busyAction}
          onStart={startRuntime}
          onStop={stopRuntime}
        />
      </header>

      {errorText && (
        <div className="border border-rose-400/50 rounded-xl bg-rose-500/10 text-rose-200 px-4 py-3 text-sm backdrop-blur">
          {errorText}
        </div>
      )}

      {/* View Tabs */}
      <div className="border border-zinc-700/50 rounded-xl bg-zinc-900/40 p-2 backdrop-blur">
        <div className="flex gap-2">
          {[
            { key: 'setup' as const, label: '系统配置', hint: '首次安装和模型配置' },
            { key: 'operations' as const, label: '运行监控', hint: '启动、日志和数据检查' },
          ].map((item) => (
            <button
              key={item.key}
              className={`flex-1 px-4 py-2.5 rounded-lg border text-sm transition-all ${
                workspaceView === item.key
                  ? 'border-emerald-400/60 bg-gradient-to-br from-emerald-500/20 to-green-500/20 text-emerald-100 shadow-lg shadow-emerald-500/20'
                  : 'border-zinc-700/60 bg-zinc-800/40 text-zinc-300 hover:border-emerald-400/40 hover:text-emerald-200'
              }`}
              onClick={() => setWorkspaceView(item.key)}
            >
              <span className="block font-semibold">{item.label}</span>
              <span className="block text-xs opacity-75 mt-0.5">{item.hint}</span>
            </button>
          ))}
        </div>
      </div>

      <main className="grid grid-cols-1 gap-5">
        {workspaceView === 'setup' && (
          <SetupView
            draft={draft}
            setDraft={setDraft}
            configPath={configPath}
            buildReady={buildReady}
            initReady={initReady}
            completedSteps={completedSteps}
            guideProgress={guideProgress}
            statusText={statusText}
            busyAction={busyAction}
            providerOptions={providerOptions}
            modelOptions={modelOptions}
            providerBaseUrlPlaceholder={providerBaseUrlPlaceholder}
            runtime={runtime}
            saveConfig={saveConfig}
            runBuild={runBuild}
            runSetup={runSetup}
          />
        )}

        {workspaceView === 'operations' && (
          <OperationsView
            runtime={runtime}
            busyAction={busyAction}
            uptimeSeries={uptimeSeries}
            activityBins={activityBins}
            streamStats={streamStats}
            logs={logs}
            filteredLogs={filteredLogs}
            logFilter={logFilter}
            setLogFilter={setLogFilter}
            logsPanelExpanded={logsPanelExpanded}
            setLogsPanelExpanded={setLogsPanelExpanded}
            dataPanelExpanded={dataPanelExpanded}
            setDataPanelExpanded={setDataPanelExpanded}
            memoryRows={memoryRows}
            runMemoryQuery={runMemoryQuery}
          />
        )}
      </main>
    </div>
  )
}

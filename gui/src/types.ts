import type { ProviderPresetOption } from './config/providers'

export type ChannelDraft = {
  webEnabled: boolean
  telegramEnabled: boolean
  telegramBotToken: string
  telegramBotUsername: string
  discordEnabled: boolean
  discordBotToken: string
  discordAllowedChannels: string
  slackEnabled: boolean
  slackBotToken: string
  slackAppToken: string
  slackAllowedChannels: string
}

export type ConfigDraft = {
  dataDir: string
  llmProvider: string
  apiKey: string
  model: string
  llmBaseUrl: string
  webHost: string
  webPort: number
  channels: ChannelDraft
}

export type SaveConfigResult = {
  configPath: string
  resolvedDataDir: string
}

export type LoadedConfigResult = {
  found: boolean
  configPath: string
  resolvedDataDir: string
  draft: ConfigDraft | null
}

export type StepDetectionResult = {
  hasConfig: boolean
  configPath: string
  resolvedDataDir: string
  buildReady: boolean
  initReady: boolean
  queryReady: boolean
}

export type RuntimeStatus = {
  running: boolean
  pid?: number | null
  uptimeSeconds?: number | null
  startedAt?: string | null
}

export type LogEntry = {
  timestamp: string
  stream: string
  line: string
}

export type CommandRunResult = {
  success: boolean
  exitCode: number
  stdout: string
  stderr: string
}

export type LogFilter = 'all' | 'system' | 'stdout' | 'stderr'

export type WorkspaceView = 'setup' | 'operations'

export type StreamStat = {
  key: 'system' | 'stdout' | 'stderr'
  label: string
  count: number
  ratio: number
}

export type { ProviderPresetOption }

import { UptimeLineChart, ActivityBars } from '../components/Charts'
import type { RuntimeStatus, LogEntry, LogFilter, StreamStat } from '../types'

type OperationsViewProps = {
  runtime: RuntimeStatus
  busyAction: string
  uptimeSeries: number[]
  activityBins: number[]
  streamStats: StreamStat[]
  logs: LogEntry[]
  filteredLogs: LogEntry[]
  logFilter: LogFilter
  setLogFilter: (filter: LogFilter) => void
  logsPanelExpanded: boolean
  setLogsPanelExpanded: (expanded: boolean) => void
  dataPanelExpanded: boolean
  setDataPanelExpanded: (expanded: boolean) => void
  memoryRows: string[][]
  runMemoryQuery: () => void
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

export function OperationsView({
  runtime,
  busyAction,
  uptimeSeries,
  activityBins,
  streamStats,
  filteredLogs,
  logFilter,
  setLogFilter,
  logsPanelExpanded,
  setLogsPanelExpanded,
  dataPanelExpanded,
  setDataPanelExpanded,
  memoryRows,
  runMemoryQuery,
}: OperationsViewProps) {
  const runningRatio = uptimeSeries.length > 0
    ? Math.round((uptimeSeries.filter(v => v > 0).length / uptimeSeries.length) * 100)
    : 0

  return (
    <section className="flex flex-col gap-5">
      {/* Status Card */}
      <article className="border border-zinc-700/50 rounded-2xl p-5 bg-gradient-to-br from-zinc-800/50 via-zinc-900/60 to-zinc-950/70 backdrop-blur shadow-xl">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h2 className="text-lg font-semibold text-zinc-100">系统状态</h2>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3">
            <span className="block text-xs text-zinc-400 mb-1">运行状态</span>
            <strong className="text-sm text-zinc-100">{runtime.running ? '● 运行中' : '○ 未启动'}</strong>
          </div>
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3">
            <span className="block text-xs text-zinc-400 mb-1">运行时长</span>
            <strong className="text-sm text-zinc-100">{formatUptime(runtime.uptimeSeconds)}</strong>
          </div>
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3">
            <span className="block text-xs text-zinc-400 mb-1">进程编号</span>
            <strong className="text-sm text-zinc-100">{runtime.pid ?? '-'}</strong>
          </div>
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3">
            <span className="block text-xs text-zinc-400 mb-1">启动时间</span>
            <strong className="text-sm text-zinc-100">{formatStartedAt(runtime.startedAt)}</strong>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3">
            <h3 className="text-xs font-medium mb-2 text-zinc-300">运行时长趋势</h3>
            <UptimeLineChart points={uptimeSeries} />
            <p className="text-xs text-zinc-400 mt-2">数据点: {uptimeSeries.length}</p>
          </div>

          <div className="border border-zinc-700/60 rounded-xl bg-zinc-800/40 p-3">
            <h3 className="text-xs font-medium mb-2 text-zinc-300">活跃度 (近 36 分钟)</h3>
            <ActivityBars bins={activityBins} />
            <p className="text-xs text-zinc-400 mt-2">每柱 = 3 分钟</p>
          </div>
        </div>

        <div className="flex flex-col gap-2 mb-3">
          {streamStats.map((stat) => (
            <div key={stat.key} className="flex flex-col gap-1">
              <div className="flex justify-between text-xs text-zinc-300">
                <span>{stat.label}</span>
                <strong>{stat.count}</strong>
              </div>
              <div className="h-2 rounded-full bg-zinc-800 border border-zinc-700/60 overflow-hidden">
                <div
                  className={`h-full bg-gradient-to-r transition-all ${
                    stat.key === 'stderr'
                      ? 'from-rose-600 to-rose-400'
                      : stat.key === 'system'
                        ? 'from-amber-500 to-amber-300'
                        : 'from-emerald-600 to-emerald-400'
                  }`}
                  style={{ width: `${Math.round(stat.ratio * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        <p className="text-xs text-zinc-400">系统稳定性：{runningRatio}%</p>
      </article>

      {/* Data Validation Card */}
      <article className="border border-zinc-700/50 rounded-2xl p-5 bg-gradient-to-br from-zinc-800/50 via-zinc-900/60 to-zinc-950/70 backdrop-blur shadow-xl">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="text-lg font-semibold text-zinc-100">数据验证</h2>
          <div className="flex gap-2">
            <button
              className="border border-zinc-600 rounded-xl bg-zinc-800/80 text-zinc-200 px-3 py-2 text-sm font-semibold hover:border-emerald-400/60 hover:text-emerald-100 transition-all"
              onClick={() => setDataPanelExpanded(!dataPanelExpanded)}
            >
              {dataPanelExpanded ? '收起' : '展开'}
            </button>
            <button
              className="border border-zinc-600 rounded-xl bg-zinc-800/80 text-zinc-200 px-3 py-2 text-sm font-semibold hover:border-emerald-400/60 hover:text-emerald-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              disabled={busyAction === 'query'}
              onClick={runMemoryQuery}
            >
              {busyAction === 'query' ? '加载中...' : '刷新数据'}
            </button>
          </div>
        </div>

        {dataPanelExpanded ? (
          <>
            <p className="text-xs text-zinc-400 mb-3">
              显示最近 20 条记忆记录，用于验证数据存储是否正常。
            </p>

            <div className="border border-zinc-700/60 rounded-xl bg-zinc-950/60 overflow-auto max-h-64">
              {memoryRows.length === 0 ? (
                <div className="text-xs text-zinc-400 p-4">暂无数据，运行后点击"刷新数据"。</div>
              ) : (
                <table className="w-full text-xs border-collapse min-w-[680px]">
                  <thead>
                    <tr className="bg-zinc-800/80 text-zinc-200 sticky top-0">
                      <th className="px-3 py-2 text-left border-b border-zinc-700/40">ID</th>
                      <th className="px-3 py-2 text-left border-b border-zinc-700/40">Chat ID</th>
                      <th className="px-3 py-2 text-left border-b border-zinc-700/40">Channel</th>
                      <th className="px-3 py-2 text-left border-b border-zinc-700/40">External Chat</th>
                      <th className="px-3 py-2 text-left border-b border-zinc-700/40">Category</th>
                      <th className="px-3 py-2 text-left border-b border-zinc-700/40">Embedding Model</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memoryRows.map((row, rowIdx) => (
                      <tr key={rowIdx} className="border-b border-zinc-700/30 hover:bg-zinc-800/30">
                        {Array.from({ length: 6 }).map((_, colIdx) => (
                          <td key={colIdx} className="px-3 py-2 text-zinc-300">{row[colIdx] || '-'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        ) : (
          <p className="text-xs text-zinc-400">
            当前已折叠。点击"展开"可查看数据样本表，点击"刷新数据"即可立即拉取。
          </p>
        )}
      </article>

      {/* Logs Card */}
      <article className="border border-zinc-700/50 rounded-2xl p-5 bg-gradient-to-br from-zinc-800/50 via-zinc-900/60 to-zinc-950/70 backdrop-blur shadow-xl min-h-[320px]">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="text-lg font-semibold text-zinc-100">运行日志</h2>
          <div className="flex gap-1.5 flex-wrap">
            <button
              className="px-3 py-1.5 text-xs rounded-lg border border-zinc-600/60 bg-zinc-800/60 text-zinc-200 hover:border-emerald-400/60 transition-all"
              onClick={() => setLogsPanelExpanded(!logsPanelExpanded)}
            >
              {logsPanelExpanded ? '收起' : '展开'}
            </button>
            {logsPanelExpanded && (
              (['all', 'system', 'stdout', 'stderr'] as const).map((item) => (
                <button
                  key={item}
                  className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
                    logFilter === item
                      ? 'border-emerald-400 bg-emerald-500/20 text-emerald-100'
                      : 'border-zinc-600/60 bg-zinc-800/60 text-zinc-300 hover:border-emerald-400/60'
                  }`}
                  onClick={() => setLogFilter(item)}
                >
                  {item === 'all' ? '全部' : item}
                </button>
              ))
            )}
          </div>
        </div>

        {logsPanelExpanded ? (
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-950/60 p-3 min-h-[220px] max-h-[340px] overflow-auto text-xs">
            {filteredLogs.length === 0 ? (
              <div className="text-zinc-400">暂无日志</div>
            ) : (
              filteredLogs.map((entry, idx) => (
                <div
                  key={`${entry.timestamp}-${idx}`}
                  className="grid grid-cols-[166px_74px_1fr] gap-2 py-1 border-b border-zinc-700/30 last:border-0"
                >
                  <span className="text-zinc-400">{entry.timestamp}</span>
                  <span className={`${
                    entry.stream === 'stderr' ? 'text-rose-300' :
                    entry.stream === 'system' ? 'text-amber-300' :
                    'text-emerald-300'
                  }`}>
                    [{entry.stream}]
                  </span>
                  <span className="text-zinc-200">{entry.line}</span>
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="border border-zinc-700/60 rounded-xl bg-zinc-950/40 p-4 text-xs text-zinc-400">
            日志面板已折叠，点击"展开"可继续查看实时输出。
          </div>
        )}
      </article>
    </section>
  )
}

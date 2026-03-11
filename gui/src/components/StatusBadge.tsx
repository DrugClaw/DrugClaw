type StatusBadgeProps = {
  running: boolean
  progress: number
  canStart: boolean
  busyAction: string
  onStart: () => void
  onStop: () => void
}

export function StatusBadge({
  running,
  progress,
  canStart,
  busyAction,
  onStart,
  onStop,
}: StatusBadgeProps) {
  return (
    <div className="flex flex-col gap-2 items-end">
      <div className={`min-w-[110px] text-center px-3 py-2 rounded-full border font-bold text-xs tracking-wide transition-all ${
        running
          ? 'border-emerald-400/60 bg-emerald-500/20 text-emerald-100 shadow-lg shadow-emerald-500/25'
          : 'border-zinc-500/40 bg-zinc-500/10 text-zinc-300'
      }`}>
        {running ? '● 运行中' : '○ 未启动'}
      </div>
      {progress > 0 && (
        <div className="text-xs font-semibold px-3 py-1 rounded-full border border-emerald-400/50 bg-emerald-500/15 text-emerald-100">
          {progress}% 就绪
        </div>
      )}
      <div className="flex gap-2">
        <button
          className="border border-emerald-400/60 rounded-xl bg-gradient-to-br from-emerald-500/40 to-green-500/40 text-white px-3 py-1.5 text-xs font-semibold hover:from-emerald-500/50 hover:to-green-500/50 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-emerald-500/20"
          disabled={busyAction === 'start' || running || !canStart}
          onClick={onStart}
        >
          {busyAction === 'start' ? '启动中...' : '启动助手'}
        </button>
        <button
          className="border border-zinc-600 rounded-xl bg-zinc-800/80 text-zinc-200 px-3 py-1.5 text-xs font-semibold hover:border-rose-400/60 hover:text-rose-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          disabled={busyAction === 'stop' || !running}
          onClick={onStop}
        >
          {busyAction === 'stop' ? '停止中...' : '停止'}
        </button>
      </div>
    </div>
  )
}

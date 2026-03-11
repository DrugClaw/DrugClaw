export function UptimeLineChart({ points }: { points: number[] }) {
  if (points.length < 2) {
    return (
      <div className="h-[90px] border border-dashed border-zinc-600/40 rounded-lg bg-zinc-900/30 flex items-center justify-center text-xs text-zinc-400">
        启动后会生成趋势图
      </div>
    )
  }

  const max = Math.max(...points)
  const min = Math.min(...points)
  const range = Math.max(1, max - min)

  const polyline = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * 100
      const y = 90 - ((value - min) / range) * 80
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg className="w-full h-[90px] border border-emerald-500/30 rounded-lg bg-gradient-to-b from-emerald-500/10 via-zinc-900/50 to-zinc-950/70" viewBox="0 0 100 100" preserveAspectRatio="none">
      <defs>
        <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.65" />
          <stop offset="100%" stopColor="#16a34a" stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <polyline points={polyline} fill="none" stroke="url(#lineGradient)" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

export function ActivityBars({ bins }: { bins: number[] }) {
  const max = Math.max(1, ...bins)
  return (
    <div className="h-[90px] border border-emerald-500/30 rounded-lg bg-zinc-950/70 p-1.5 grid grid-cols-12 gap-1 items-end">
      {bins.map((value, idx) => {
        const height = Math.max(8, Math.round((value / max) * 100))
        return (
          <div key={idx} className="h-full flex items-end">
            <div
              className="w-full rounded-t-md bg-gradient-to-t from-emerald-600 via-emerald-400 to-emerald-300 transition-all hover:opacity-80"
              style={{ height: `${height}%` }}
            />
          </div>
        )
      })}
    </div>
  )
}

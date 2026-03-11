type ToggleProps = {
  checked: boolean
  onChange: (next: boolean) => void
  label: string
}

export function Toggle({ checked, onChange, label }: ToggleProps) {
  return (
    <label className="flex justify-between items-center gap-2.5 text-sm text-zinc-200 cursor-pointer group">
      <span className="group-hover:text-white transition-colors">{label}</span>
      <button
        type="button"
        className={`w-11 h-6 border rounded-full p-0.5 transition-all ${
          checked
            ? 'bg-emerald-500/30 border-emerald-400/70 shadow-[0_0_12px_rgba(52,211,153,0.3)]'
            : 'bg-zinc-700/50 border-zinc-600 hover:border-zinc-500'
        }`}
        onClick={() => onChange(!checked)}
      >
        <span className={`block w-[18px] h-[18px] rounded-full bg-white shadow-md transition-transform ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`} />
      </button>
    </label>
  )
}

import { ReactNode } from 'react'

type FieldProps = {
  label: string
  hint?: string
  children: ReactNode
}

export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-zinc-300">{label}</span>
      {children}
      {hint && <span className="text-xs text-zinc-400">{hint}</span>}
    </label>
  )
}

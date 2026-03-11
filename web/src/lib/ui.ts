import { cva } from 'class-variance-authority'

export const messageBubbleVariants = cva(
  'w-[min(88%,860px)] rounded-2xl border px-4 py-3 shadow-[0_6px_16px_rgba(15,23,42,0.05)]',
  {
  variants: {
    role: {
      bot: 'border-slate-200 bg-white',
      user: 'border-teal-300/70 bg-teal-50/60',
    },
  },
  defaultVariants: {
    role: 'bot',
  },
  },
)

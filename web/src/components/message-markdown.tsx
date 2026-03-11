import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'

type MessageMarkdownProps = {
  content: string
}

export function MessageMarkdown({ content }: MessageMarkdownProps) {
  return (
    <div className="mt-2 text-[15px] leading-7 text-slate-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          p: ({ children }) => <p className="my-2 whitespace-pre-wrap">{children}</p>,
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          h1: ({ children }) => <h1 className="mt-5 mb-2 text-xl font-semibold">{children}</h1>,
          h2: ({ children }) => <h2 className="mt-4 mb-2 text-lg font-semibold">{children}</h2>,
          h3: ({ children }) => <h3 className="mt-3 mb-1 text-base font-semibold">{children}</h3>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-teal-700 underline underline-offset-2">
              {children}
            </a>
          ),
          code: ({ className, children }) => {
            const isBlock = className?.includes('language-')
            if (isBlock) {
              return (
                <code className="block overflow-x-auto rounded-xl bg-slate-900 p-4 font-mono text-xs text-slate-100">
                  {children}
                </code>
              )
            }
            return <code className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[12px]">{children}</code>
          },
          pre: ({ children }) => <pre className="my-2 overflow-x-auto">{children}</pre>,
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-4 border-teal-300 bg-teal-50/40 py-1 pl-3 text-slate-700">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border border-slate-300 bg-slate-100 px-2 py-1.5">{children}</th>,
          td: ({ children }) => <td className="border border-slate-300 px-2 py-1.5">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

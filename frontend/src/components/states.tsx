/** ChangeText, loading / empty / error states. Every block handles its own three states (§6.2). */
import { AlertTriangle, ChevronDown, Inbox } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { ApiError } from '@/api/client'
import { trendOf } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Button } from './ui'

/** Coloured by market convention via --up/--down; always carries a +/− sign too (§6.5 可访问性). */
export function ChangeText({ value, children, className }: { value: number | null | undefined; children: ReactNode; className?: string }) {
  const trend = trendOf(value)
  return <span className={cn('num', trend === 'up' ? 'text-up' : trend === 'down' ? 'text-down' : 'text-flat', className)}>{children}</span>
}

export function EmptyState({ title, hint, className }: { title: string; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-1.5 py-10 text-center', className)}>
      <Inbox className="h-5 w-5 text-subtle" aria-hidden />
      <div className="text-[13px] text-muted">{title}</div>
      {hint && <div className="text-[12px] text-subtle">{hint}</div>}
    </div>
  )
}

export function ErrorState({ error, title, onRetry, className }: { error: unknown; title?: string; onRetry?: () => void; className?: string }) {
  const [open, setOpen] = useState(false)
  const info = error instanceof ApiError ? error.info : { category: 'unknown', message: String(error), detail: null }
  return (
    <div role="alert" className={cn('flex flex-col items-center justify-center gap-2 px-4 py-8 text-center', className)}>
      <AlertTriangle className="h-5 w-5 text-warn" aria-hidden />
      <div className="text-[13px] text-fg">{title ?? '数据加载失败'}</div>
      <div className="max-w-md text-[12px] text-muted">{info.message}</div>
      <div className="text-[11px] text-subtle">
        错误类别：<span className="font-mono">{info.category}</span>
      </div>
      <div className="flex items-center gap-2">
        {onRetry && (
          <Button size="sm" onClick={onRetry}>
            重试
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          技术详情 <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
        </Button>
      </div>
      {open && (
        <pre className="max-h-40 max-w-xl overflow-auto rounded border border-line bg-app p-2 text-left font-mono text-[11px] whitespace-pre-wrap text-subtle">
          {`category=${info.category}\n${info.detail ?? ''}`}
        </pre>
      )}
    </div>
  )
}

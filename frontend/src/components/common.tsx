/** Small pieces shared by the 自选 / 排行 / 市场 / 新闻 pages. */
import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { RefreshCw, Undo2, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { api, type Schemas } from '@/api/client'
import { cn } from '@/lib/utils'
import { Button, Tip } from './ui'

type QuoteStatus = Schemas['WatchlistQuoteRow']['status']

const STATUS: Record<QuoteStatus, { label: string; tone: string; hint: string }> = {
  latest: { label: '最新', tone: 'text-muted border-line', hint: '最近一次行情接口返回的数据' },
  cached: { label: '缓存', tone: 'text-warn border-warn/30 bg-warn-weak', hint: '行情接口暂不可用，显示本地缓存' },
  old_date: { label: '旧日期', tone: 'text-warn border-warn/30', hint: '行情日期早于其它股票（可能停牌或数据滞后），不计入当日统计' },
  missing: { label: '缺失', tone: 'text-error border-error/30 bg-error-weak', hint: '没有取到行情' },
}

export function QuoteStatusTag({ status, date }: { status: QuoteStatus; date?: string | null }) {
  const s = STATUS[status]
  return (
    <Tip content={date && status === 'old_date' ? `${s.hint}（${date}）` : s.hint}>
      <span tabIndex={0} className={cn('inline-flex h-5 items-center rounded border px-1.5 text-[11px] whitespace-nowrap', s.tone)}>
        {s.label}
      </span>
    </Tip>
  )
}

export function RefreshButton({
  body,
  invalidate,
  tip,
  label,
}: {
  body: Schemas['RefreshRequest']
  invalidate: QueryKey[]
  tip: string
  label?: string
}) {
  const client = useQueryClient()
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try {
      await api.post('/api/refresh', body)
      await Promise.all(invalidate.map((queryKey) => client.invalidateQueries({ queryKey })))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Tip content={tip}>
      <Button variant="ghost" size={label ? 'sm' : 'iconSm'} onClick={run} disabled={busy} aria-label={label ?? '刷新'}>
        <RefreshCw className={cn('h-3.5 w-3.5', busy && 'animate-spin')} />
        {label}
      </Button>
    </Tip>
  )
}

/** "已移除 X · 撤销" bar (§6.4 UndoToast). Disappears after ``timeoutMs``. */
export function UndoToast({ message, onUndo, onClose, timeoutMs = 8000 }: { message: ReactNode; onUndo: () => void; onClose: () => void; timeoutMs?: number }) {
  useEffect(() => {
    const id = setTimeout(onClose, timeoutMs)
    return () => clearTimeout(id)
  }, [onClose, timeoutMs])
  return (
    <div role="status" className="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-md border border-line-strong bg-panel py-1.5 pr-1.5 pl-3 text-[13px] shadow-pop">
      <span>{message}</span>
      <Button size="sm" variant="accent" onClick={onUndo}>
        <Undo2 className="h-3.5 w-3.5" /> 撤销
      </Button>
      <Button size="iconSm" variant="ghost" onClick={onClose} aria-label="关闭">
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}

/** Page title row: title, optional subtitle, and right-aligned controls. */
export function PageHeader({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 pt-4 pb-3">
      <h1 className="text-[17px] font-semibold">{title}</h1>
      {sub && <span className="text-[12px] text-subtle">{sub}</span>}
      <div className="flex-1" />
      {children}
    </header>
  )
}

/** Proportional up / flat / down bar (§6.4 BreadthBar). Colours follow the enclosing data-market. */
export function BreadthBar({ up, down, flat, className }: { up: number; down: number; flat: number; className?: string }) {
  const total = up + down + flat || 1
  const pct = (n: number) => `${((n / total) * 100).toFixed(1)}%`
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-raised" role="img" aria-label={`上涨 ${up}，平盘 ${flat}，下跌 ${down}`}>
        <div className="bg-up" style={{ width: pct(up) }} />
        <div className="bg-flat/60" style={{ width: pct(flat) }} />
        <div className="bg-down" style={{ width: pct(down) }} />
      </div>
      <div className="num flex justify-between text-[12px]">
        <span className="text-up">
          涨 {up.toLocaleString('en-US')} <span className="text-subtle">{pct(up)}</span>
        </span>
        <span className="text-muted">平 {flat.toLocaleString('en-US')}</span>
        <span className="text-down">
          <span className="text-subtle">{pct(down)}</span> 跌 {down.toLocaleString('en-US')}
        </span>
      </div>
    </div>
  )
}

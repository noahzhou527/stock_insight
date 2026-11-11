/** Data-status badge for every data block (§4.2): source · time · freshness, details on hover. */
import type { Meta } from '@/api/client'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Tip } from './ui'

const LABEL: Record<Meta['freshness'], string> = {
  live: '实时',
  closed: '已收盘',
  provisional: '盘中合成',
  fallback: '备用源',
  cached: '缓存',
  demo: '演示数据，勿用于决策',
}

const TONE: Record<Meta['freshness'], string> = {
  live: 'text-accent border-accent/30 bg-accent-weak',
  closed: 'text-muted border-line bg-panel',
  provisional: 'text-accent border-accent/30 bg-accent-weak',
  fallback: 'text-warn border-warn/30 bg-warn-weak',
  cached: 'text-warn border-warn/30 bg-warn-weak',
  demo: 'text-error border-error/30 bg-error-weak',
}

function asOfText(asOf: Meta['as_of']): string | null {
  if (!asOf) return null
  return asOf.length > 10 ? formatTime(asOf, true) : asOf
}

export function freshnessLabel(meta: Meta): string {
  if (meta.freshness === 'fallback') return `备用源：${meta.source ?? '未知'}`
  if (meta.freshness === 'cached') return `缓存${meta.fetched_at ? `（${formatTime(meta.fetched_at + 'Z', true)}）` : ''}`
  return LABEL[meta.freshness]
}

export function DataStatusBadge({ meta, className, compact = false }: { meta: Meta | undefined; className?: string; compact?: boolean }) {
  if (!meta) return null
  const asOf = asOfText(meta.as_of)
  const details = (
    <div className="space-y-0.5">
      <div>
        <span className="text-subtle">来源</span> {meta.source ?? '—'}
      </div>
      {asOf && (
        <div>
          <span className="text-subtle">数据时间</span> {asOf}
        </div>
      )}
      {meta.fetched_at && (
        <div>
          <span className="text-subtle">取数时间</span> {formatTime(meta.fetched_at + 'Z', true)}
        </div>
      )}
      {meta.note && <div className="pt-1 text-muted">{meta.note}</div>}
      {meta.errors?.map((e, i) => (
        <div key={i} className="pt-1 text-warn">
          {e.message}
        </div>
      ))}
    </div>
  )
  return (
    <Tip content={details} side="bottom">
      <span
        tabIndex={0}
        className={cn(
          'inline-flex h-5 cursor-default items-center gap-1.5 rounded border px-1.5 text-[11px] font-medium whitespace-nowrap',
          TONE[meta.freshness],
          className,
        )}
      >
        {meta.freshness === 'live' && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden />}
        {!compact && meta.source && meta.freshness !== 'fallback' && <span className="text-muted">{meta.source}</span>}
        {!compact && asOf && meta.freshness !== 'cached' && <span className="num text-muted">{asOf}</span>}
        <span>{freshnessLabel(meta)}</span>
      </span>
    </Tip>
  )
}

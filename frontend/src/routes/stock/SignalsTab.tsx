/** 技术信号摘要 (B3): descriptive fixed rules — no buy/sell wording, no composite score. */
import type { Schemas } from '@/api/client'
import { useSignals } from '@/api/queries'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { InfoTip } from '@/components/InfoTip'
import { ErrorState } from '@/components/states'
import { Skeleton } from '@/components/ui'
import type { IndicatorKey } from '@/lib/indicatorHelp'
import type { Market } from '@/lib/format'
import { cn } from '@/lib/utils'

type Signal = Schemas['SignalOut']

const TONE: Record<Signal['tone'], string> = {
  up: 'text-up border-up/35',
  down: 'text-down border-down/35',
  warn: 'text-warn border-warn/35 bg-warn-weak',
  neutral: 'text-muted border-line',
  info: 'text-subtle border-line border-dashed',
}

const HELP: Partial<Record<string, IndicatorKey>> = { trend: 'ma', rsi: 'rsi', macd: 'macd', volatility: 'volatility' }

export function SignalsTab({ market, symbol, rsi }: { market: Market; symbol: string; rsi: number }) {
  const query = useSignals(market, symbol, rsi)
  if (query.isError && !query.data) return <ErrorState error={query.error} title="技术信号加载失败" onRetry={() => query.refetch()} />
  if (!query.data) {
    return (
      <div className="grid gap-2 p-4 md:grid-cols-2">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-14" />
        ))}
      </div>
    )
  }
  const { title, disclaimer, signals, meta } = query.data
  return (
    <section className="p-4" aria-label={title}>
      <header className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-[14px] font-semibold">{title}</h2>
        <span className="text-[12px] text-subtle">{disclaimer}</span>
        <div className="flex-1" />
        <DataStatusBadge meta={meta} compact />
      </header>
      <ul className="grid gap-2 md:grid-cols-2">
        {signals.map((signal) => (
          <li key={signal.key} className="flex items-start gap-3 rounded-md border border-line bg-panel px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1 text-[12px] text-muted">
                {signal.name}
                {HELP[signal.key] && <InfoTip topic={HELP[signal.key]!} />}
              </div>
              <div className="num mt-0.5 text-[13px] text-fg">{signal.description}</div>
            </div>
            <span className={cn('shrink-0 rounded border px-1.5 py-0.5 text-[12px] font-medium whitespace-nowrap', TONE[signal.tone])}>{signal.status}</span>
          </li>
        ))}
      </ul>
      {meta.note && <p className="mt-3 text-[12px] text-subtle">{meta.note}</p>}
    </section>
  )
}

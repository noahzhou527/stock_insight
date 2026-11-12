/** /market/:market — 指数卡片、涨跌家数、指数分时 (§6.3, §8 市场). One failing index only affects its own card. */
import { Link, useNavigate } from '@tanstack/react-router'
import { AlertTriangle } from 'lucide-react'
import { useLayoutEffect, useRef, useState } from 'react'
import type { Schemas } from '@/api/client'
import { useIndexIntraday, useMarketOverview, useMarketSession } from '@/api/queries'
import { IntradayChart } from '@/charts/IntradayChart'
import { BreadthBar, PageHeader, RefreshButton } from '@/components/common'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { ChangeText, EmptyState, ErrorState } from '@/components/states'
import { Skeleton, Tip } from '@/components/ui'
import { DASH, formatAmount, formatPct, formatPrice, formatSigned, type Market } from '@/lib/format'
import { cn } from '@/lib/utils'
import { marketRoute } from './router'
import type { MarketSearch } from './search'

type Card = Schemas['IndexCard']

const MARKETS: { value: Market; label: string }[] = [
  { value: 'CN', label: 'A 股' },
  { value: 'US', label: '美股' },
  { value: 'KR', label: '韩股' },
]

function IndexCard({ card, market, selected, onSelect }: { card: Card; market: Market; selected: boolean; onSelect: () => void }) {
  if (card.error && card.price == null) {
    return (
      <div className="flex min-h-[132px] flex-col gap-1 rounded-md border border-line bg-panel p-3">
        <div className="flex items-baseline gap-2">
          <span className="text-[13px] font-medium">{card.name}</span>
          <span className="num text-[11px] text-subtle">{card.display_code}</span>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-1 text-center">
          <AlertTriangle className="h-4 w-4 text-warn" aria-hidden />
          <span className="text-[12px] text-muted">{card.error.message}</span>
          <span className="font-mono text-[10px] text-subtle">{card.error.category}</span>
        </div>
      </div>
    )
  }
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'flex min-h-[132px] cursor-pointer flex-col gap-1.5 rounded-md border bg-panel p-3 text-left transition-colors',
        selected ? 'border-accent/60 shadow-[inset_0_0_0_1px_var(--accent)]' : 'border-line hover:border-line-strong',
      )}
    >
      <div className="flex w-full items-baseline gap-2">
        <span className="text-[13px] font-medium">{card.name}</span>
        <span className="num text-[11px] text-subtle">{card.display_code}</span>
        <span className="flex-1" />
        {card.error && (
          <Tip content={card.error.message}>
            <AlertTriangle className="h-3.5 w-3.5 text-warn" aria-label={card.error.message} />
          </Tip>
        )}
      </div>
      <ChangeText value={card.change} className="text-[22px] leading-tight font-semibold">
        {formatPrice(card.price, 'CNY')}
      </ChangeText>
      <ChangeText value={card.change} className="text-[13px]">
        {formatSigned(card.change, 2)}　{formatPct(card.change_pct)}
      </ChangeText>
      {market === 'CN' && (
        <div className="num space-y-0.5 text-[11px] text-muted">
          <div>
            成交额 <span className="text-fg">{formatAmount(card.amount, 'CN')}</span>
            {card.amount_change_pct != null && (
              <span className="ml-1">
                较上日 <ChangeText value={card.amount_change_pct}>{formatPct(card.amount_change_pct, 1)}</ChangeText>
              </span>
            )}
          </div>
          {card.constituents && (
            <div>
              成分股 <span className="text-up">涨 {card.constituents.up}</span> · <span className="text-down">跌 {card.constituents.down}</span> · 平 {card.constituents.flat}
            </div>
          )}
        </div>
      )}
      <div className="mt-auto text-[11px] text-subtle">
        {card.trade_date ?? DASH} · {card.source ?? DASH}
      </div>
    </button>
  )
}

function Breadth({ breadth, market }: { breadth: Schemas['BreadthOut']; market: Market }) {
  return (
    <section className="rounded-md border border-line bg-panel p-3" aria-label="涨跌家数">
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="text-[13px] font-semibold">{market === 'CN' ? '全 A 涨跌家数' : '美股涨跌家数'}</h2>
        {!breadth.full_market && <span className="rounded border border-warn/40 bg-warn-weak px-1.5 text-[11px] text-warn">非全市场</span>}
        <span className="text-[12px] text-subtle">
          {breadth.source}
          {breadth.total != null && ` · 共 ${breadth.total.toLocaleString('en-US')} 只`}
        </span>
        <div className="flex-1" />
        {/* 回退时数据来自本地股票池，徽标的来源以 breadth.source 为准 */}
        {breadth.meta && <DataStatusBadge meta={{ ...breadth.meta, source: breadth.source ?? breadth.meta.source }} compact />}
      </header>
      {breadth.up != null && breadth.down != null ? (
        <BreadthBar up={breadth.up} down={breadth.down} flat={breadth.flat ?? 0} />
      ) : (
        <div className="py-2 text-[12px] text-muted">{breadth.error?.message ?? '暂无涨跌家数'}</div>
      )}
      {breadth.meta?.note && <p className="mt-2 text-[12px] text-subtle">{breadth.meta.note}</p>}
    </section>
  )
}

function useHeight(ref: React.RefObject<HTMLDivElement | null>) {
  const [height, setHeight] = useState(420)
  useLayoutEffect(() => {
    const update = () => setHeight(Math.max(320, Math.min(560, Math.round(window.innerHeight * 0.48))))
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [ref])
  return height
}

function IndexIntradayPanel({ market, card }: { market: Market; card: Card }) {
  const query = useIndexIntraday(market, card.symbol)
  const session = useMarketSession(market)
  const ref = useRef<HTMLDivElement>(null)
  const height = useHeight(ref)
  const data = query.data
  return (
    <section ref={ref} className="rounded-md border border-line bg-panel" aria-label="指数分时">
      <header className="flex flex-wrap items-center gap-2 px-3 pt-3 pb-2">
        <h2 className="text-[13px] font-semibold">{card.name} 分时</h2>
        {data && (
          <span className="num text-[12px] text-subtle">
            {data.trade_date}
            {market !== 'CN' && ' · 最近一个交易日'}
          </span>
        )}
        <div className="flex-1" />
        <DataStatusBadge meta={data?.meta} compact />
      </header>
      {query.isError && !data ? (
        <ErrorState error={query.error} title="指数分时加载失败" onRetry={() => query.refetch()} />
      ) : !data || !session ? (
        <div className="p-3" style={{ height }}>
          <Skeleton className="h-full" />
        </div>
      ) : data.points.length === 0 ? (
        <EmptyState title="暂无分时数据" className="py-16" />
      ) : (
        <IntradayChart
          points={data.points}
          preClose={data.pre_close}
          tradeDate={data.trade_date}
          sessions={session.sessions}
          market={market}
          currency="CNY"
          height={height}
          sub={market === 'CN' ? 'amount' : 'volume'}
        />
      )}
    </section>
  )
}

export function MarketPage() {
  const { market: raw } = marketRoute.useParams()
  const market = (MARKETS.some((m) => m.value === raw.toUpperCase()) ? raw.toUpperCase() : 'CN') as Market
  const search = marketRoute.useSearch() as MarketSearch
  const navigate = useNavigate({ from: marketRoute.fullPath })
  const query = useMarketOverview(market)
  const cards = query.data?.indices ?? []
  const selected = cards.find((c) => c.symbol === search.index) ?? cards.find((c) => !c.error || c.price != null)

  return (
    <div data-market={market} className="min-w-0 pb-10">
      <PageHeader title="市场概览">
        <div className="inline-flex rounded-md border border-line bg-panel p-0.5" role="tablist" aria-label="市场">
          {MARKETS.map((m) => (
            <Link
              key={m.value}
              to="/market/$market"
              params={{ market: m.value }}
              role="tab"
              aria-selected={m.value === market}
              className={cn(
                'h-6 rounded-[5px] px-2.5 text-[12px] leading-6 font-medium',
                m.value === market ? 'bg-raised text-fg shadow-[inset_0_0_0_1px_var(--line-strong)]' : 'text-muted hover:text-fg',
              )}
            >
              {m.label}
            </Link>
          ))}
        </div>
        <DataStatusBadge meta={query.data?.meta} />
        <RefreshButton body={{ target: 'market', market }} invalidate={[['market', market]]} tip="只刷新这个市场的指数与涨跌家数" />
      </PageHeader>

      <div className="space-y-3 px-4">
        {query.isError && !query.data ? (
          <ErrorState error={query.error} title="市场概览加载失败" onRetry={() => query.refetch()} className="rounded-md border border-line bg-panel" />
        ) : !query.data ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
            {Array.from({ length: market === 'CN' ? 5 : market === 'US' ? 4 : 1 }, (_, i) => (
              <Skeleton key={i} className="h-[132px]" />
            ))}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3" role="list" aria-label="指数">
              {cards.map((card) => (
                <div role="listitem" key={card.symbol}>
                  <IndexCard
                    card={card}
                    market={market}
                    selected={card.symbol === selected?.symbol}
                    onSelect={() => navigate({ search: { index: card.symbol }, replace: true })}
                  />
                </div>
              ))}
            </div>
            {query.data.breadth && <Breadth breadth={query.data.breadth} market={market} />}
            {selected ? <IndexIntradayPanel market={market} card={selected} /> : <EmptyState title="没有可显示分时的指数" className="py-10" />}
          </>
        )}
      </div>
    </div>
  )
}

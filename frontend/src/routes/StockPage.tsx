/** /stock/:market/:symbol — quote header, attribute bar, K-line / intraday (P3 sample; tabs arrive in P4). */
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { RefreshCw } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/api/client'
import { useBars, useIntraday, useMarketSession, useSnapshot } from '@/api/queries'
import { IntradayChart } from '@/charts/IntradayChart'
import { KlineChart, type SubChart } from '@/charts/KlineChart'
import { MA_COLORS } from '@/charts/chartTheme'
import { rememberStock } from '@/lib/nav'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { AttributeBar, QuoteHeader } from '@/components/QuoteHeader'
import { EmptyState, ErrorState } from '@/components/states'
import { Button, Segmented, Skeleton, Tip } from '@/components/ui'
import type { Market } from '@/lib/format'
import { localToday, RANGE_LABELS, RANGES, resolveRange } from '@/lib/range'
import { cn } from '@/lib/utils'
import { parseMa, stockRoute, type StockSearch } from './router'

const MA_CHOICES = [5, 10, 20, 30, 50, 60, 120]

/** Chart height: fill the viewport below the header blocks (1080p shows the whole chart without scrolling). */
function useChartHeight(ref: React.RefObject<HTMLDivElement | null>) {
  const [height, setHeight] = useState(480)
  useLayoutEffect(() => {
    const update = () => {
      const top = ref.current?.getBoundingClientRect().top ?? 300
      setHeight(Math.max(360, Math.round(window.innerHeight - top - 52)))
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [ref])
  return height
}

export function StockPage() {
  const { market: rawMarket, symbol } = stockRoute.useParams()
  const market = rawMarket.toUpperCase() as Market
  const search = stockRoute.useSearch() as StockSearch
  const navigate = useNavigate({ from: stockRoute.fullPath })
  const session = useMarketSession(market)
  const today = session?.today ?? localToday()
  const { start, end } = resolveRange(search.range, today, search.start, search.end)
  const currency = market === 'KR' ? search.cur : market === 'US' ? 'USD' : 'CNY'
  const apiCurrency = market === 'KR' && currency === 'USD' ? 'USD' : undefined
  const maPeriods = parseMa(search.ma)
  const maKeys = maPeriods.map((p) => `ma${p}`)

  const set = (patch: Partial<StockSearch>) => navigate({ search: (prev) => ({ ...prev, ...patch }), replace: false })

  useEffect(() => rememberStock(market, symbol), [market, symbol])

  const ready = Boolean(session)
  const snapshot = useSnapshot(market, symbol, { start, end, currency: apiCurrency }, ready)
  const bars = useBars(market, symbol, { start, end, ma: search.ma, currency: apiCurrency }, ready && search.chart === 'kline')
  const intraday = useIntraday(market, symbol, apiCurrency, search.chart === 'intraday')

  const chartRef = useRef<HTMLDivElement>(null)
  const chartHeight = useChartHeight(chartRef)
  const queryClient = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)
  const refresh = async () => {
    setRefreshing(true)
    try {
      await api.post('/api/refresh', { target: 'stock', market, symbol })
      await queryClient.invalidateQueries({ predicate: (q) => q.queryKey[1] === market && q.queryKey[2] === symbol })
    } finally {
      setRefreshing(false)
    }
  }

  const sessions = useMemo(() => session?.sessions ?? [], [session])
  const notice = noticeFor(snapshot.data?.meta, search.chart === 'kline' ? bars.data?.meta : intraday.data?.meta)

  return (
    <div data-market={market} className="min-w-0">
      <QuoteHeader market={market} symbol={symbol} snapshot={snapshot.data} currency={currency} onCurrency={(cur) => set({ cur: cur as 'KRW' | 'USD' })} />
      {snapshot.isError && !snapshot.data ? (
        <ErrorState error={snapshot.error} title="报价加载失败" onRetry={() => snapshot.refetch()} className="border-y border-line py-4" />
      ) : (
        <AttributeBar snapshot={snapshot.data} market={market} currency={currency} />
      )}
      {notice && <div className="border-b border-warn/30 bg-warn-weak px-4 py-1.5 text-[12px] text-warn">{notice}</div>}

      <div className="flex flex-wrap items-center gap-2 px-4 py-2">
        <Segmented
          label="图表类型"
          value={search.chart}
          onChange={(chart) => set({ chart })}
          options={[
            { value: 'kline', label: 'K线' },
            { value: 'intraday', label: '分时' },
          ]}
        />
        {search.chart === 'kline' && (
          <>
            <Segmented label="日期区间" value={search.range} onChange={(range) => set({ range })} options={RANGES.filter((r) => r !== 'custom').map((r) => ({ value: r, label: RANGE_LABELS[r] }))} />
            <div className="flex items-center gap-1" role="group" aria-label="均线">
              <span className="pr-0.5 text-[11px] text-subtle">MA</span>
              {MA_CHOICES.map((p) => {
                const on = maPeriods.includes(p)
                return (
                  <button
                    key={p}
                    type="button"
                    aria-pressed={on}
                    onClick={() => set({ ma: (on ? maPeriods.filter((x) => x !== p) : [...maPeriods, p]).sort((a, b) => a - b).join(',') })}
                    className={cn(
                      'num h-6 cursor-pointer rounded border px-1.5 text-[11px] transition-colors',
                      on ? 'border-line-strong bg-raised' : 'border-transparent text-subtle hover:text-fg',
                    )}
                    style={on ? { color: MA_COLORS[maPeriods.indexOf(p) % MA_COLORS.length] } : undefined}
                  >
                    {p}
                  </button>
                )
              })}
            </div>
            <Segmented label="副图" value={search.sub} onChange={(sub) => set({ sub })} options={[{ value: 'volume', label: '成交量' }, { value: 'amount', label: '成交额' }]} />
          </>
        )}
        <div className="flex-1" />
        <DataStatusBadge meta={search.chart === 'kline' ? bars.data?.meta : intraday.data?.meta} compact />
        <Tip content="只刷新这只股票的行情">
          <Button variant="ghost" size="iconSm" onClick={refresh} disabled={refreshing} aria-label="刷新">
            <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
          </Button>
        </Tip>
      </div>

      <div ref={chartRef} className="border-y border-line bg-panel">
        {search.chart === 'kline' ? (
          bars.isError && !bars.data ? (
            <ErrorState error={bars.error} title="日线加载失败" onRetry={() => bars.refetch()} className="py-24" />
          ) : !bars.data ? (
            <div style={{ height: chartHeight }} className="p-4">
              <Skeleton className="h-full w-full" />
            </div>
          ) : bars.data.bars.length === 0 ? (
            <EmptyState title="所选区间没有日线数据" hint="可能尚未上市或停牌，试试更长的区间" className="py-24" />
          ) : (
            <KlineChart
              bars={bars.data.bars}
              indicators={bars.data.indicators}
              maKeys={maKeys.filter((k) => k in bars.data.indicators)}
              sub={search.sub as SubChart}
              market={market}
              currency={currency}
              height={chartHeight}
            />
          )
        ) : intraday.isError && !intraday.data ? (
          <ErrorState error={intraday.error} title="分时加载失败" onRetry={() => intraday.refetch()} className="py-24" />
        ) : !intraday.data || !session ? (
          <div style={{ height: chartHeight }} className="p-4">
            <Skeleton className="h-full w-full" />
          </div>
        ) : intraday.data.points.length === 0 ? (
          <EmptyState title="暂无分时数据" className="py-24" />
        ) : (
          <IntradayChart
            points={intraday.data.points}
            preClose={intraday.data.pre_close}
            tradeDate={intraday.data.trade_date}
            sessions={sessions}
            market={market}
            currency={currency}
            height={chartHeight}
          />
        )}
      </div>
      <div className="flex h-10 items-center gap-5 px-4 text-[13px] text-subtle" aria-label="分区（P4 实现）">
        {['技术信号', '财务报表', '同业对比', '数据明细'].map((t) => (
          <span key={t}>{t}</span>
        ))}
        <span className="text-[11px]">· 样张阶段，P4 接入</span>
      </div>
    </div>
  )
}

/** Only abnormal states get a prominent bar (§6.2): cache, fallback source, demo. */
function noticeFor(...metas: (import('@/api/client').Meta | undefined)[]): string | null {
  for (const meta of metas) {
    if (!meta) continue
    if (meta.freshness === 'cached') return `上游数据源暂不可用，部分数据来自本地缓存。${meta.note ?? ''}`
    if (meta.freshness === 'fallback') return `主数据源不可用，当前使用备用源：${meta.source}`
    if (meta.freshness === 'demo') return '演示数据，勿用于决策'
  }
  return null
}

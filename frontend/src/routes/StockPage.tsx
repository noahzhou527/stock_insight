/** /stock/:market/:symbol — quote header, attribute bar, K-line / intraday, and the four tabs (§6.2). */
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { RefreshCw } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { api, type Meta } from '@/api/client'
import { useBars, useIntraday, useMarketSession, useSnapshot } from '@/api/queries'
import { IntradayChart } from '@/charts/IntradayChart'
import { KlineChart } from '@/charts/KlineChart'
import { BBI_COLOR, MA_COLORS } from '@/charts/chartTheme'
import { rememberStock } from '@/lib/nav'
import { updatePrefs } from '@/lib/prefs'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { InfoTip } from '@/components/InfoTip'
import { AttributeBar, QuoteHeader } from '@/components/QuoteHeader'
import { EmptyState, ErrorState } from '@/components/states'
import { Button, Segmented, Skeleton, Tip } from '@/components/ui'
import type { Market } from '@/lib/format'
import { localToday, RANGE_LABELS, RANGES, resolveRange, type RangeKey } from '@/lib/range'
import { cn } from '@/lib/utils'
import { stockRoute } from './router'
import { parseMa, TABS, type StockSearch, type SubKey, type TabKey } from './search'
import { DataTab } from './stock/DataTab'
import { FinancialsTab } from './stock/FinancialsTab'
import { PeersTab } from './stock/PeersTab'
import { SignalsTab } from './stock/SignalsTab'

const INDICATOR_KEYS = ['ma', 'bbi', 'boll', 'rsi', 'sub'] as const
const MA_CHOICES = [5, 10, 20, 30, 50, 60, 120]
const RSI_PERIODS = Array.from({ length: 15 }, (_, i) => i + 7) // 7–21
const TAB_LABELS: Record<TabKey, string> = { signals: '技术信号', financials: '财务报表', peers: '同业对比', data: '数据明细' }
const SUB_OPTIONS: { value: SubKey; label: string }[] = [
  { value: 'volume', label: '成交量' },
  { value: 'amount', label: '成交额' },
  { value: 'rsi', label: 'RSI' },
  { value: 'macd', label: 'MACD' },
]

/** Chart height: fill the viewport below the header blocks (1080p shows the whole chart without scrolling). */
function useChartHeight(ref: React.RefObject<HTMLDivElement | null>) {
  const [height, setHeight] = useState(480)
  useLayoutEffect(() => {
    const update = () => {
      const top = ref.current?.getBoundingClientRect().top ?? 300
      setHeight(Math.max(360, Math.round(window.innerHeight - top - window.scrollY - 52)))
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [ref])
  return height
}

function Chip({ on, color, onClick, children }: { on: boolean; color?: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn('num h-6 cursor-pointer rounded border px-1.5 text-[11px] transition-colors', on ? 'border-line-strong bg-raised text-fg' : 'border-transparent text-subtle hover:text-fg')}
      style={on && color ? { color } : undefined}
    >
      {children}
    </button>
  )
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

  const set = (patch: Partial<StockSearch>) => {
    // Indicator choices become the default for every stock (§6.6 偏好：默认均线与指标、副图类型).
    const indicator = INDICATOR_KEYS.filter((k) => k in patch)
    if (indicator.length) {
      const next = { ...search, ...patch }
      updatePrefs({ stock_defaults: { ma: next.ma, bbi: next.bbi, boll: next.boll, rsi: next.rsi, sub: next.sub } })
    }
    navigate({ search: (prev) => ({ ...prev, ...patch }), replace: false })
  }
  const setRange = (range: RangeKey) => set(range === 'custom' ? { range, start, end } : { range, start: undefined, end: undefined })

  useEffect(() => rememberStock(market, symbol), [market, symbol])

  const ready = Boolean(session)
  const snapshot = useSnapshot(market, symbol, { start, end, currency: apiCurrency }, ready)
  const bars = useBars(
    market,
    symbol,
    { start, end, ma: search.ma, bbi: search.bbi, boll: search.boll, rsi: search.rsi, currency: apiCurrency },
    ready && (search.chart === 'kline' || search.tab === 'data'),
  )
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

  // The chart fills the first screen and takes the mouse wheel (zoom), so opening a tab brings it into view.
  const tabsRef = useRef<HTMLDivElement>(null)
  const openTab = (tab: TabKey) => {
    set({ tab })
    requestAnimationFrame(() => tabsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  const sessions = useMemo(() => session?.sessions ?? [], [session])
  const chartMeta = search.chart === 'kline' ? bars.data?.meta : intraday.data?.meta
  const notices = noticesFor(snapshot.data?.meta, chartMeta)

  return (
    <div data-market={market} className="min-w-0">
      <QuoteHeader market={market} symbol={symbol} snapshot={snapshot.data} failed={snapshot.isError && !snapshot.data} currency={currency} onCurrency={(cur) => set({ cur: cur as 'KRW' | 'USD' })} />
      {snapshot.isError && !snapshot.data ? (
        <ErrorState error={snapshot.error} title="报价加载失败" onRetry={() => snapshot.refetch()} className="border-y border-line py-4" />
      ) : (
        <AttributeBar snapshot={snapshot.data} market={market} currency={currency} />
      )}
      {notices.map((notice) => (
        <div
          key={notice.text}
          role="status"
          className={cn('border-b px-4 py-1.5 text-[12px]', notice.tone === 'warn' ? 'border-warn/30 bg-warn-weak text-warn' : notice.tone === 'error' ? 'border-error/30 bg-error-weak text-error' : 'border-accent/25 bg-accent-weak text-accent')}
        >
          {notice.text}
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 px-4 py-2">
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
            <Segmented label="日期区间" value={search.range} onChange={setRange} options={RANGES.map((r) => ({ value: r, label: RANGE_LABELS[r] }))} />
            {search.range === 'custom' && (
              <div className="flex items-center gap-1 text-[12px] text-subtle" role="group" aria-label="自定义日期">
                <input
                  type="date"
                  aria-label="开始日期"
                  value={start}
                  max={end ?? today}
                  onChange={(e) => e.target.value && e.target.value <= (end ?? today) && set({ start: e.target.value })}
                  className="num h-7 rounded-md border border-line bg-panel px-1.5 text-fg [color-scheme:inherit]"
                />
                至
                <input
                  type="date"
                  aria-label="结束日期"
                  value={end ?? today}
                  min={start}
                  max={today}
                  onChange={(e) => e.target.value && e.target.value >= start && set({ end: e.target.value >= today ? undefined : e.target.value })}
                  className="num h-7 rounded-md border border-line bg-panel px-1.5 text-fg [color-scheme:inherit]"
                />
              </div>
            )}
            <div className="flex items-center gap-0.5" role="group" aria-label="主图指标">
              <span className="pr-0.5 text-[11px] text-subtle">MA</span>
              <InfoTip topic="ma" />
              {MA_CHOICES.map((p) => {
                const on = maPeriods.includes(p)
                return (
                  <Chip
                    key={p}
                    on={on}
                    color={MA_COLORS[maPeriods.indexOf(p) % MA_COLORS.length]}
                    onClick={() => set({ ma: (on ? maPeriods.filter((x) => x !== p) : [...maPeriods, p]).sort((a, b) => a - b).join(',') })}
                  >
                    {p}
                  </Chip>
                )
              })}
              <span className="mx-1 h-3.5 w-px bg-line" aria-hidden />
              <Chip on={search.bbi} color={BBI_COLOR} onClick={() => set({ bbi: !search.bbi })}>
                BBI
              </Chip>
              <InfoTip topic="bbi" />
              <Chip on={search.boll} color="var(--accent)" onClick={() => set({ boll: !search.boll })}>
                BOLL
              </Chip>
              <InfoTip topic="boll" />
            </div>
            <div className="flex items-center gap-1">
              <Segmented label="副图" value={search.sub} onChange={(sub) => set({ sub })} options={SUB_OPTIONS} />
              {search.sub === 'rsi' && (
                <>
                  <label className="flex items-center gap-1 text-[11px] text-subtle">
                    周期
                    <select
                      value={search.rsi}
                      onChange={(e) => set({ rsi: Number(e.target.value) })}
                      className="num h-7 cursor-pointer rounded-md border border-line bg-panel px-1 text-[12px] text-fg"
                    >
                      {RSI_PERIODS.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </label>
                  <InfoTip topic="rsi" />
                </>
              )}
              {search.sub === 'macd' && <InfoTip topic="macd" />}
            </div>
          </>
        )}
        {search.chart === 'intraday' && (
          <Segmented label="副图" value={search.sub === 'amount' ? 'amount' : 'volume'} onChange={(sub) => set({ sub })} options={SUB_OPTIONS.slice(0, 2)} />
        )}
        <div className="flex-1" />
        <DataStatusBadge meta={chartMeta} compact />
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
              bbi={search.bbi && 'bbi' in bars.data.indicators}
              boll={search.boll && 'boll_upper' in bars.data.indicators}
              rsiPeriod={search.rsi}
              sub={search.sub}
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
            sub={search.sub === 'amount' ? 'amount' : 'volume'}
          />
        )}
      </div>

      <div ref={tabsRef} role="tablist" aria-label="个股分区" className="scroll-mt-12 flex h-10 items-stretch gap-1 border-b border-line px-3">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`tab-${tab}`}
            aria-selected={search.tab === tab}
            aria-controls="stock-tabpanel"
            onClick={() => openTab(tab)}
            className={cn(
              '-mb-px cursor-pointer border-b-2 px-2.5 text-[13px] transition-colors',
              search.tab === tab ? 'border-accent font-medium text-fg' : 'border-transparent text-muted hover:text-fg',
            )}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="stock-tabpanel" aria-labelledby={`tab-${search.tab}`} className="min-h-[320px]">
        {search.tab === 'signals' && <SignalsTab market={market} symbol={symbol} rsi={search.rsi} />}
        {search.tab === 'financials' && <FinancialsTab market={market} symbol={symbol} currency={currency} apiCurrency={apiCurrency} />}
        {search.tab === 'peers' && <PeersTab market={market} symbol={symbol} />}
        {search.tab === 'data' &&
          (bars.isError && !bars.data ? (
            <ErrorState error={bars.error} title="日线加载失败" onRetry={() => bars.refetch()} />
          ) : !bars.data ? (
            <div className="p-4">
              <Skeleton className="h-64" />
            </div>
          ) : (
            <DataTab data={bars.data} market={market} symbol={symbol} currency={currency} apiCurrency={apiCurrency} rsiPeriod={search.rsi} start={start} end={end} />
          ))}
      </div>
    </div>
  )
}

interface Notice {
  tone: 'warn' | 'error' | 'info'
  text: string
}

/** Only abnormal states get a prominent bar (§6.2): cache, fallback source, demo, intraday-built bar. */
function noticesFor(...metas: (Meta | undefined)[]): Notice[] {
  const notices = new Map<string, Notice>()
  const add = (tone: Notice['tone'], text: string) => notices.set(`${tone}:${text.slice(0, 12)}`, { tone, text })
  for (const meta of metas) {
    if (!meta) continue
    if (meta.freshness === 'cached') add('warn', `上游数据源暂不可用，部分数据来自本地缓存。${meta.note ?? ''}`)
    else if (meta.freshness === 'fallback') add('warn', `主数据源不可用，当前使用备用源：${meta.source ?? '未知'}`)
    else if (meta.freshness === 'demo') add('error', '演示数据，勿用于决策')
    else if (meta.freshness === 'provisional') add('info', '当日 K 线由分时合成，成交额可能与结算值略有偏差')
  }
  return [...notices.values()]
}

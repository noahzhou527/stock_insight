/**
 * URL search params of every page (§6.1): parsed leniently (malformed values fall back to defaults) and
 * written back without the values that equal the defaults, so URLs stay short.
 * The stock page's indicator defaults come from the user's prefs (§6.6).
 */
import { RANGES, type RangeKey } from '@/lib/range'
import { getPrefs } from '@/lib/prefs'

const DATE = /^\d{4}-\d{2}-\d{2}$/

// ------------------------------------------------------------------ stock
export const SUBS = ['volume', 'amount', 'rsi', 'macd'] as const
export type SubKey = (typeof SUBS)[number]
export const TABS = ['signals', 'financials', 'peers', 'data'] as const
export type TabKey = (typeof TABS)[number]

export interface StockSearch {
  range: RangeKey
  start?: string
  end?: string
  ma: string // "5,10,20" — kept as plain text so the URL stays readable
  bbi: boolean
  boll: boolean
  rsi: number // RSI 周期 7–21
  sub: SubKey
  chart: 'kline' | 'intraday'
  cur: 'KRW' | 'USD'
  tab: TabKey
}

export const STOCK_SEARCH_DEFAULTS = { range: '1y', ma: '5,10,20', bbi: false, boll: false, rsi: 14, sub: 'volume', chart: 'kline', cur: 'KRW', tab: 'signals' } as const

export function parseMa(value: string): number[] {
  return [...new Set(value.split(',').map(Number).filter((v) => Number.isInteger(v) && v >= 2 && v <= 250))].sort((a, b) => a - b)
}

function flag(value: unknown, fallback: boolean): boolean {
  if (value === undefined) return fallback
  return value === true || value === 'true' || value === 1 || value === '1'
}

function rsiPeriod(value: unknown, fallback = 14): number {
  const n = Number(value)
  return value !== undefined && Number.isInteger(n) && n >= 7 && n <= 21 ? n : fallback
}

/** Built-in defaults overlaid with the user's saved indicator choices. */
export function stockDefaults(): StockSearch {
  const saved = getPrefs().stock_defaults ?? {}
  return {
    ...STOCK_SEARCH_DEFAULTS,
    ma: typeof saved.ma === 'string' ? parseMa(saved.ma).join(',') : STOCK_SEARCH_DEFAULTS.ma,
    bbi: typeof saved.bbi === 'boolean' ? saved.bbi : false,
    boll: typeof saved.boll === 'boolean' ? saved.boll : false,
    rsi: rsiPeriod(saved.rsi),
    sub: SUBS.includes(saved.sub as SubKey) ? (saved.sub as SubKey) : 'volume',
  }
}

export function validateStockSearch(raw: Record<string, unknown>, defaults: StockSearch = stockDefaults()): StockSearch {
  return {
    range: RANGES.includes(raw.range as RangeKey) ? (raw.range as RangeKey) : defaults.range,
    start: typeof raw.start === 'string' && DATE.test(raw.start) ? raw.start : undefined,
    end: typeof raw.end === 'string' && DATE.test(raw.end) ? raw.end : undefined,
    ma: raw.ma === undefined ? defaults.ma : parseMa(String(raw.ma)).join(','),
    bbi: flag(raw.bbi, defaults.bbi),
    boll: flag(raw.boll, defaults.boll),
    rsi: rsiPeriod(raw.rsi, defaults.rsi),
    sub: SUBS.includes(raw.sub as SubKey) ? (raw.sub as SubKey) : defaults.sub,
    chart: raw.chart === 'intraday' ? 'intraday' : 'kline',
    cur: raw.cur === 'USD' ? 'USD' : 'KRW',
    tab: TABS.includes(raw.tab as TabKey) ? (raw.tab as TabKey) : defaults.tab,
  }
}

// ------------------------------------------------------------------ watchlist
export const WATCH_SORTS = ['order', 'change_pct', 'change', 'price', 'amount', 'quote_time', 'name', 'change_5d', 'change_20d', 'turnover', 'amplitude', 'market_cap', 'pe_ttm'] as const
export type WatchSort = (typeof WATCH_SORTS)[number]
export type Dir = 'asc' | 'desc'

export interface WatchlistSearch {
  q: string
  sort: WatchSort
  dir: Dir
}

export function watchlistDefaults(): WatchlistSearch {
  const saved = getPrefs().watchlist_sort
  return {
    q: '',
    sort: WATCH_SORTS.includes(saved?.sort as WatchSort) ? (saved!.sort as WatchSort) : 'order',
    dir: saved?.dir === 'asc' ? 'asc' : 'desc',
  }
}

export function validateWatchlistSearch(raw: Record<string, unknown>, defaults: WatchlistSearch = watchlistDefaults()): WatchlistSearch {
  return {
    q: typeof raw.q === 'string' ? raw.q.slice(0, 40) : defaults.q,
    sort: WATCH_SORTS.includes(raw.sort as WatchSort) ? (raw.sort as WatchSort) : defaults.sort,
    dir: raw.dir === 'asc' || raw.dir === 'desc' ? raw.dir : defaults.dir,
  }
}

// ------------------------------------------------------------------ rankings
export const RANK_METRICS = ['change_pct', 'amount', 'market_cap', 'pe_ttm', 'quarter_profit'] as const
export type RankMetric = (typeof RANK_METRICS)[number]
export const RANK_SORTS = [...RANK_METRICS, 'price', 'quarter_profit_yoy', 'name', 'group'] as const
export type RankSort = (typeof RANK_SORTS)[number]

export interface RankingsSearch {
  metric: RankMetric
  sort?: RankSort // defaults to the metric itself
  dir?: Dir // defaults to the metric's natural direction (PE ascending, others descending)
}

export const metricDir = (metric: RankMetric): Dir => (metric === 'pe_ttm' ? 'asc' : 'desc')

export function validateRankingsSearch(raw: Record<string, unknown>): RankingsSearch {
  const metric = RANK_METRICS.includes(raw.metric as RankMetric) ? (raw.metric as RankMetric) : 'change_pct'
  return {
    metric,
    sort: RANK_SORTS.includes(raw.sort as RankSort) ? (raw.sort as RankSort) : undefined,
    dir: raw.dir === 'asc' || raw.dir === 'desc' ? raw.dir : undefined,
  }
}

// ------------------------------------------------------------------ market / news
export interface MarketSearch {
  index?: string // index symbol for the intraday chart; first card by default
}

export function validateMarketSearch(raw: Record<string, unknown>): MarketSearch {
  return { index: typeof raw.index === 'string' && raw.index.length <= 20 ? raw.index : undefined }
}

export interface NewsSearch {
  source?: string
}

export function validateNewsSearch(raw: Record<string, unknown>): NewsSearch {
  return { source: typeof raw.source === 'string' && raw.source.length <= 20 ? raw.source : undefined }
}

/** Drop keys whose value equals the current default (or is empty), keeping URLs short and shareable. */
export function withoutDefaults<T extends object>(search: T, defaults: Partial<T>): Partial<T> {
  return Object.fromEntries(
    Object.entries(search).filter(([key, value]) => value !== undefined && value !== '' && defaults[key as keyof T] !== value),
  ) as Partial<T>
}

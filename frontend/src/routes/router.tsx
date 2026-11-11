/** Code-based TanStack Router tree (§6.1). All page state lives in the URL. */
import { createRootRoute, createRoute, createRouter, redirect, stripSearchParams } from '@tanstack/react-router'
import { AppShell } from '@/components/AppShell'
import { lastStock } from '@/lib/nav'
import { EmptyState } from '@/components/states'
import { RANGES, type RangeKey } from '@/lib/range'
import { StockPage } from './StockPage'

export interface StockSearch {
  range: RangeKey
  start?: string
  end?: string
  ma: string // "5,10,20" — kept as plain text so the URL stays readable
  sub: 'volume' | 'amount'
  chart: 'kline' | 'intraday'
  cur: 'KRW' | 'USD'
}

const DATE = /^\d{4}-\d{2}-\d{2}$/

export const STOCK_SEARCH_DEFAULTS = { range: '1y', ma: '5,10,20', sub: 'volume', chart: 'kline', cur: 'KRW' } as const

export function parseMa(value: string): number[] {
  return [...new Set(value.split(',').map(Number).filter((v) => Number.isInteger(v) && v >= 2 && v <= 250))].sort((a, b) => a - b)
}

/** Lenient: unknown or malformed values fall back to defaults instead of erroring. */
export function validateStockSearch(raw: Record<string, unknown>): StockSearch {
  return {
    range: RANGES.includes(raw.range as RangeKey) ? (raw.range as RangeKey) : '1y',
    start: typeof raw.start === 'string' && DATE.test(raw.start) ? raw.start : undefined,
    end: typeof raw.end === 'string' && DATE.test(raw.end) ? raw.end : undefined,
    ma: raw.ma === undefined ? '5,10,20' : parseMa(String(raw.ma)).join(','),
    sub: raw.sub === 'amount' ? 'amount' : 'volume',
    chart: raw.chart === 'intraday' ? 'intraday' : 'kline',
    cur: raw.cur === 'USD' ? 'USD' : 'KRW',
  }
}

const rootRoute = createRootRoute({ component: AppShell })

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    const { market, symbol } = lastStock()
    throw redirect({ to: '/stock/$market/$symbol', params: { market, symbol } })
  },
})

export const stockRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/stock/$market/$symbol',
  // Typed as Partial so links need not pass search; validateStockSearch always fills every field.
  validateSearch: (raw: Record<string, unknown>): Partial<StockSearch> => validateStockSearch(raw),
  // Shareable URLs carry only what differs from the defaults, e.g. /stock/CN/300308.SZ?range=3m
  search: { middlewares: [stripSearchParams(STOCK_SEARCH_DEFAULTS)] },
  component: StockPage,
})

function Placeholder({ title }: { title: string }) {
  return (
    <div className="p-6">
      <h1 className="mb-2 text-[16px] font-semibold">{title}</h1>
      <EmptyState title="这一页在 P5 实现" hint="样张阶段先确认个股页的视觉方向" />
    </div>
  )
}

const watchlistRoute = createRoute({ getParentRoute: () => rootRoute, path: '/watchlist', component: () => <Placeholder title="自选" /> })
const marketRoute = createRoute({ getParentRoute: () => rootRoute, path: '/market/$market', component: () => <Placeholder title="市场概览" /> })
const rankingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/rankings', component: () => <Placeholder title="A股股票池排行" /> })
const newsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/news', component: () => <Placeholder title="新闻" /> })

const routeTree = rootRoute.addChildren([indexRoute, stockRoute, watchlistRoute, marketRoute, rankingsRoute, newsRoute])

export const router = createRouter({
  routeTree,
  defaultNotFoundComponent: () => <EmptyState title="页面不存在" className="py-24" />,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

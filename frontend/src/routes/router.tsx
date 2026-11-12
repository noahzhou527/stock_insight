/** Code-based TanStack Router tree (§6.1). All page state lives in the URL; parsing rules are in search.ts. */
import { createRootRoute, createRoute, createRouter, lazyRouteComponent, redirect } from '@tanstack/react-router'
import { AppShell } from '@/components/AppShell'
import { EmptyState } from '@/components/states'
import { lastPage } from '@/lib/nav'
import {
  stockDefaults,
  validateMarketSearch,
  validateNewsSearch,
  validateRankingsSearch,
  validateStockSearch,
  validateWatchlistSearch,
  watchlistDefaults,
  withoutDefaults,
  type MarketSearch,
  type NewsSearch,
  type RankingsSearch,
  type StockSearch,
  type WatchlistSearch,
} from './search'

// Each page is its own chunk; the chart library is only loaded by the pages that draw charts.
const StockPage = lazyRouteComponent(() => import('./StockPage'), 'StockPage')
const WatchlistPage = lazyRouteComponent(() => import('./WatchlistPage'), 'WatchlistPage')
const MarketPage = lazyRouteComponent(() => import('./MarketPage'), 'MarketPage')
const RankingsPage = lazyRouteComponent(() => import('./RankingsPage'), 'RankingsPage')
const NewsPage = lazyRouteComponent(() => import('./NewsPage'), 'NewsPage')

const rootRoute = createRootRoute({ component: AppShell })

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ href: lastPage(), replace: true })
  },
})

// Search is typed as Partial so links need not pass it; each validator always fills every field.
export const stockRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/stock/$market/$symbol',
  validateSearch: (raw: Record<string, unknown>): Partial<StockSearch> => validateStockSearch(raw),
  // Shareable URLs carry only what differs from the defaults, e.g. /stock/CN/300308.SZ?range=3m
  search: { middlewares: [({ search, next }) => withoutDefaults(next(search) as StockSearch, stockDefaults())] },
  component: StockPage,
})

export const watchlistRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/watchlist',
  validateSearch: (raw: Record<string, unknown>): Partial<WatchlistSearch> => validateWatchlistSearch(raw),
  search: { middlewares: [({ search, next }) => withoutDefaults(next(search) as WatchlistSearch, watchlistDefaults())] },
  component: WatchlistPage,
})

export const marketRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/market/$market',
  validateSearch: (raw: Record<string, unknown>): MarketSearch => validateMarketSearch(raw),
  component: MarketPage,
})

export const rankingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/rankings',
  validateSearch: (raw: Record<string, unknown>): Partial<RankingsSearch> => validateRankingsSearch(raw),
  search: { middlewares: [({ search, next }) => withoutDefaults(next(search) as RankingsSearch, { metric: 'change_pct' })] },
  component: RankingsPage,
})

export const newsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/news',
  validateSearch: (raw: Record<string, unknown>): NewsSearch => validateNewsSearch(raw),
  component: NewsPage,
})

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

/** TanStack Query hooks. Polling: 30 s, only while that market is in session and the page is visible (§4.4). */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, instrumentPath, type Schemas } from './client'
import type { Market } from '@/lib/format'

const POLL_MS = 30_000

export function useSessions() {
  return useQuery({
    queryKey: ['sessions'],
    queryFn: ({ signal }) => api.get<Schemas['SessionsResponse']>('/api/market/sessions', undefined, signal),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useMarketSession(market: Market) {
  const sessions = useSessions()
  return sessions.data?.markets.find((m) => m.market === market)
}

function usePoll(market: Market) {
  const session = useMarketSession(market)
  return session?.trading ? POLL_MS : false
}

export function useUniverse() {
  return useQuery({
    queryKey: ['universe'],
    queryFn: ({ signal }) => api.get<Schemas['UniverseGroup'][]>('/api/universe', undefined, signal),
    staleTime: 10 * 60_000,
  })
}

export function useWatchlistItems() {
  return useQuery({
    queryKey: ['watchlist', 'items'],
    queryFn: ({ signal }) => api.get<Schemas['WatchlistItem'][]>('/api/watchlist/items', undefined, signal),
  })
}

export function useSearch(q: string) {
  const text = q.trim()
  return useQuery({
    queryKey: ['search', text],
    queryFn: ({ signal }) => api.get<Schemas['SearchResult'][]>('/api/instruments/search', { q: text }, signal),
    enabled: text.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

export interface BarsParams {
  start: string
  end?: string
  ma: string
  bbi?: boolean
  boll?: boolean
  rsi?: number
  currency?: string
}

export function useBars(market: Market, symbol: string, params: BarsParams, enabled = true) {
  const poll = usePoll(market)
  return useQuery({
    queryKey: ['bars', market, symbol, params],
    queryFn: ({ signal }) => api.get<Schemas['BarsResponse']>(instrumentPath(market, symbol, '/bars'), { ...params }, signal),
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

export function useSnapshot(market: Market, symbol: string, params: { start: string; end?: string; currency?: string }, enabled = true) {
  const poll = usePoll(market)
  return useQuery({
    queryKey: ['snapshot', market, symbol, params],
    queryFn: ({ signal }) => api.get<Schemas['SnapshotResponse']>(instrumentPath(market, symbol, '/snapshot'), { ...params }, signal),
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

export function useIntraday(market: Market, symbol: string, currency?: string, enabled = true) {
  const poll = usePoll(market)
  return useQuery({
    queryKey: ['intraday', market, symbol, currency],
    queryFn: ({ signal }) => api.get<Schemas['IntradayResponse']>(instrumentPath(market, symbol, '/intraday'), { currency }, signal),
    enabled,
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

export function useSignals(market: Market, symbol: string, rsi: number) {
  const poll = usePoll(market)
  return useQuery({
    queryKey: ['signals', market, symbol, rsi],
    queryFn: ({ signal }) => api.get<Schemas['SignalsResponse']>(instrumentPath(market, symbol, '/signals'), { rsi }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

/** 财报与同业对比一天变不了几次：不轮询，10 分钟内不重取。 */
export function useFinancials(market: Market, symbol: string, currency?: string) {
  return useQuery({
    queryKey: ['financials', market, symbol, currency],
    queryFn: ({ signal }) => api.get<Schemas['FinancialsResponse']>(instrumentPath(market, symbol, '/financials'), { currency }, signal),
    staleTime: 10 * 60_000,
  })
}

export function usePeers(market: Market, symbol: string) {
  return useQuery({
    queryKey: ['peers', market, symbol],
    queryFn: ({ signal }) => api.get<Schemas['PeersResponse']>(instrumentPath(market, symbol, '/peers'), undefined, signal),
    staleTime: 10 * 60_000,
  })
}

export function useWatchlistQuotes() {
  const poll = usePoll('CN')
  return useQuery({
    queryKey: ['watchlist', 'quotes'],
    queryFn: ({ signal }) => api.get<Schemas['WatchlistQuotesResponse']>('/api/watchlist/quotes', undefined, signal),
    placeholderData: keepPreviousData,
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

/** Quotes are the same for every metric; only 季度净利润 makes the backend fetch financial reports. */
export function useRankings(metric: string) {
  const poll = usePoll('CN')
  const queryMetric = metric === 'quarter_profit' ? 'quarter_profit' : 'change_pct'
  return useQuery({
    queryKey: ['rankings', queryMetric],
    queryFn: ({ signal }) => api.get<Schemas['RankingsResponse']>('/api/rankings', { metric: queryMetric }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

export function useMarketOverview(market: Market) {
  const poll = usePoll(market)
  return useQuery({
    queryKey: ['market', market, 'overview'],
    queryFn: ({ signal }) => api.get<Schemas['MarketOverview']>(`/api/market/${market}/overview`, undefined, signal),
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

export function useIndexIntraday(market: Market, symbol: string | undefined) {
  const poll = usePoll(market)
  return useQuery({
    queryKey: ['market', market, 'index', symbol],
    queryFn: ({ signal }) => api.get<Schemas['IndexIntraday']>(`/api/market/${market}/indices/${encodeURIComponent(symbol!)}/intraday`, undefined, signal),
    enabled: Boolean(symbol),
    placeholderData: keepPreviousData,
    refetchInterval: poll,
    staleTime: 20_000,
  })
}

/** 新闻不随行情轮询；5 分钟内视为新鲜，手动刷新可立即重取。 */
export function useNews() {
  return useQuery({
    queryKey: ['news'],
    queryFn: ({ signal }) => api.get<Schemas['NewsResponse']>('/api/news', { hours: 72 }, signal),
    staleTime: 5 * 60_000,
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => api.get<Schemas['HealthResponse']>('/api/health', undefined, signal),
    refetchInterval: 60_000,
  })
}

/**
 * User preferences stored by the backend (/api/prefs, §6.6): theme, default chart indicators, watchlist
 * columns and sort, sidebar, last visited page. Loaded once before the router starts; writes are merged
 * and debounced. localStorage only caches the theme (for the no-flash inline script in index.html).
 */
import { create } from 'zustand'
import { api } from '@/api/client'

export interface StockDefaults {
  ma?: string
  bbi?: boolean
  boll?: boolean
  rsi?: number
  sub?: 'volume' | 'amount' | 'rsi' | 'macd'
}

export interface Prefs {
  theme?: 'system' | 'dark' | 'light'
  stock_defaults?: StockDefaults
  watchlist_columns?: string[]
  watchlist_sort?: { sort: string; dir: 'asc' | 'desc' }
  sidebar_open?: boolean
  last_page?: string
  last_stock?: { market: string; symbol: string }
}

interface PrefsState {
  prefs: Prefs
  loaded: boolean
  update: (patch: Partial<Prefs>) => void
}

let pending: Partial<Prefs> = {}
let timer: ReturnType<typeof setTimeout> | undefined
const SAVE_DELAY_MS = 600

function flush() {
  const body = pending
  pending = {}
  timer = undefined
  if (Object.keys(body).length) api.put('/api/prefs', body).catch(() => undefined) // best effort; the page keeps working
}

export const usePrefs = create<PrefsState>((set, get) => ({
  prefs: {},
  loaded: false,
  update: (patch) => {
    const changed = Object.entries(patch).filter(([k, v]) => JSON.stringify(get().prefs[k as keyof Prefs]) !== JSON.stringify(v))
    if (!changed.length) return
    const diff = Object.fromEntries(changed) as Partial<Prefs>
    set((s) => ({ prefs: { ...s.prefs, ...diff } }))
    pending = { ...pending, ...diff }
    if (timer) clearTimeout(timer)
    timer = setTimeout(flush, SAVE_DELAY_MS)
  },
}))

if (typeof window !== 'undefined') window.addEventListener('pagehide', flush)

export const getPrefs = () => usePrefs.getState().prefs
export const updatePrefs = (patch: Partial<Prefs>) => usePrefs.getState().update(patch)

/** Load prefs before first render. A slow or missing backend must not block the app: give up after 1.5 s. */
export async function loadPrefs(timeoutMs = 1500): Promise<void> {
  try {
    const prefs = await Promise.race([
      api.get<Prefs>('/api/prefs'),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error('timeout')), timeoutMs)),
    ])
    usePrefs.setState({ prefs: prefs ?? {}, loaded: true })
  } catch {
    usePrefs.setState({ loaded: true })
  }
}

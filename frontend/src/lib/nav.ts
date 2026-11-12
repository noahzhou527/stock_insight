/** Last visited stock / page and sidebar visibility, persisted through backend prefs (§6.6). */
import { create } from 'zustand'
import { getPrefs, updatePrefs } from './prefs'

const DEFAULT_STOCK = { market: 'CN', symbol: '300308.SZ' }
const DESKTOP = 1280

export function lastStock(): { market: string; symbol: string } {
  const value = getPrefs().last_stock
  return value?.market && value?.symbol ? value : DEFAULT_STOCK
}

export function rememberStock(market: string, symbol: string) {
  updatePrefs({ last_stock: { market, symbol } })
}

/** Where "/" goes: the last page visited, else the last stock. */
export function lastPage(): string {
  const page = getPrefs().last_page
  if (page && page.startsWith('/') && page !== '/') return page
  const { market, symbol } = lastStock()
  return `/stock/${market}/${encodeURIComponent(symbol)}`
}

export function rememberPage(href: string) {
  if (href && href !== '/') updatePrefs({ last_page: href })
}

const isDesktop = () => typeof window !== 'undefined' && window.innerWidth >= DESKTOP

interface UiState {
  sidebarOpen: boolean
  toggleSidebar: () => void
  setSidebar: (open: boolean) => void
}

export const useUi = create<UiState>((set, get) => ({
  sidebarOpen: isDesktop(),
  // Only the docked (desktop) state is a preference; the drawer on narrow screens always starts closed.
  toggleSidebar: () => get().setSidebar(!get().sidebarOpen),
  setSidebar: (open) => {
    set({ sidebarOpen: open })
    if (isDesktop()) updatePrefs({ sidebar_open: open })
  },
}))

/** Apply prefs that affect the shell once they are loaded. */
export function applyShellPrefs() {
  const open = getPrefs().sidebar_open
  if (isDesktop() && typeof open === 'boolean') useUi.setState({ sidebarOpen: open })
}

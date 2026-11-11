/** Small shared UI state: last visited stock (for / and the 个股 tab) and sidebar visibility. */
import { create } from 'zustand'

const LAST_STOCK_KEY = 'si-last-stock'

export function lastStock(): { market: string; symbol: string } {
  try {
    const value = JSON.parse(localStorage.getItem(LAST_STOCK_KEY) ?? 'null')
    if (value?.market && value?.symbol) return value
  } catch {
    /* ignore */
  }
  return { market: 'CN', symbol: '300308.SZ' }
}

export function rememberStock(market: string, symbol: string) {
  try {
    localStorage.setItem(LAST_STOCK_KEY, JSON.stringify({ market, symbol }))
  } catch {
    /* ignore */
  }
}

interface UiState {
  sidebarOpen: boolean
  toggleSidebar: () => void
  setSidebar: (open: boolean) => void
}

export const useUi = create<UiState>((set) => ({
  sidebarOpen: typeof window === 'undefined' ? true : window.innerWidth >= 1280,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebar: (open) => set({ sidebarOpen: open }),
}))

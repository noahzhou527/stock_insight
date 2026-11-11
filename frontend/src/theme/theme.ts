/** Theme preference (system / dark / light). index.html applies it before first paint; this keeps it in sync. */
import { create } from 'zustand'

export type ThemePref = 'system' | 'dark' | 'light'
export type Theme = 'dark' | 'light'

const KEY = 'si-theme'
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

function readPref(): ThemePref {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'dark' || value === 'light' ? value : 'system'
  } catch {
    return 'system'
  }
}

function resolve(pref: ThemePref): Theme {
  return pref === 'system' ? (media().matches ? 'dark' : 'light') : pref
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
}

interface ThemeState {
  pref: ThemePref
  theme: Theme
  setPref: (pref: ThemePref) => void
  cycle: () => void
}

export const useTheme = create<ThemeState>((set, get) => ({
  pref: readPref(),
  theme: (document.documentElement.dataset.theme as Theme) || resolve(readPref()),
  setPref: (pref) => {
    try {
      if (pref === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, pref)
    } catch {
      /* storage blocked: still switch for this session */
    }
    const theme = resolve(pref)
    apply(theme)
    set({ pref, theme })
  },
  cycle: () => {
    const order: ThemePref[] = ['system', 'dark', 'light']
    get().setPref(order[(order.indexOf(get().pref) + 1) % order.length])
  },
}))

media().addEventListener('change', () => {
  const { pref, setPref } = useTheme.getState()
  if (pref === 'system') setPref('system')
})

/** Read a CSS custom property (charts need concrete colours). */
export function cssVar(name: string, element: Element = document.documentElement): string {
  return getComputedStyle(element).getPropertyValue(name).trim()
}

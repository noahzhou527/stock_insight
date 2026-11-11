/** Top bar (个股 / 自选 / 市场 / 排行 / 新闻 + search + theme) and collapsible sidebar (§6.1). */
import { Link, Outlet, useParams, useRouterState } from '@tanstack/react-router'
import { ChevronRight, Monitor, Moon, PanelLeft, Search, Sun } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useUniverse, useWatchlistItems } from '@/api/queries'
import { lastStock, useUi } from '@/lib/nav'
import { cn } from '@/lib/utils'
import { useTheme } from '@/theme/theme'
import { SearchCommand, useSearchHotkey } from './SearchCommand'
import { Button, Kbd, Tip } from './ui'

const NAV = [
  { to: '/stock/$market/$symbol', label: '个股', match: '/stock' },
  { to: '/watchlist', label: '自选', match: '/watchlist' },
  { to: '/market/$market', label: '市场', match: '/market' },
  { to: '/rankings', label: '排行', match: '/rankings' },
  { to: '/news', label: '新闻', match: '/news' },
] as const

function ThemeButton() {
  const { pref, cycle } = useTheme()
  const Icon = pref === 'dark' ? Moon : pref === 'light' ? Sun : Monitor
  const label = pref === 'dark' ? '深色' : pref === 'light' ? '浅色' : '跟随系统'
  return (
    <Tip content={`主题：${label}（点击切换）`} side="bottom">
      <Button variant="ghost" size="icon" onClick={cycle} aria-label={`主题：${label}`}>
        <Icon className="h-4 w-4" />
      </Button>
    </Tip>
  )
}

function TopBar({ onSearch }: { onSearch: () => void }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { toggleSidebar } = useUi()
  const stock = lastStock()
  return (
    <header className="sticky top-0 z-30 flex h-11 shrink-0 items-center gap-2 border-b border-line bg-panel/95 px-2 backdrop-blur sm:gap-3 sm:px-3">
      <Button variant="ghost" size="iconSm" onClick={toggleSidebar} aria-label="切换侧栏">
        <PanelLeft className="h-4 w-4" />
      </Button>
      <Link to="/" className="flex items-center gap-2 pr-2 text-[13px] font-semibold tracking-wide text-fg">
        <span className="h-2.5 w-2.5 rounded-sm bg-accent" aria-hidden />
        <span className="hidden sm:inline">Stock Insight</span>
      </Link>
      <nav className="flex min-w-0 items-center gap-0.5 overflow-x-auto [scrollbar-width:none]" aria-label="主导航">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.match)
          const params = item.to === '/stock/$market/$symbol' ? stock : item.to === '/market/$market' ? { market: 'CN' } : undefined
          return (
            <Link
              key={item.label}
              to={item.to}
              params={params as never}
              className={cn(
                'relative flex h-11 shrink-0 items-center px-2 text-[13px] transition-colors sm:px-2.5',
                active ? 'text-fg' : 'text-muted hover:text-fg',
              )}
            >
              {item.label}
              {active && <span className="absolute inset-x-2.5 bottom-0 h-0.5 rounded-full bg-accent" />}
            </Link>
          )
        })}
      </nav>
      <div className="flex-1" />
      <button
        type="button"
        onClick={onSearch}
        aria-label="搜索代码或名称"
        className="flex h-7 shrink-0 cursor-pointer items-center gap-2 rounded-md border border-line bg-app px-2 text-[12px] text-subtle hover:border-line-strong md:w-[min(280px,32vw)] md:px-2.5"
      >
        <Search className="h-3.5 w-3.5" aria-hidden />
        <span className="hidden flex-1 truncate text-left md:inline">搜索代码或名称</span>
        <span className="hidden md:inline">
          <Kbd>Ctrl K</Kbd>
        </span>
      </button>
      <ThemeButton />
    </header>
  )
}

function SidebarGroup({ title, items, defaultOpen }: { title: string; items: { id: string; market: string; symbol: string; name: string | null }[]; defaultOpen: boolean }) {
  const params = useParams({ strict: false }) as { market?: string; symbol?: string }
  const activeId = params.market && params.symbol ? `${params.market}:${params.symbol}` : null
  const containsActive = items.some((item) => item.id === activeId)
  // null = never toggled by the user: follow "contains the open stock"
  const [toggled, setToggled] = useState<boolean | null>(null)
  const open = toggled ?? (defaultOpen || containsActive)
  const setOpen = (fn: (v: boolean) => boolean) => setToggled(fn(open))
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex h-7 w-full cursor-pointer items-center gap-1 px-3 text-[12px] font-medium text-muted hover:text-fg"
      >
        <ChevronRight className={cn('h-3.5 w-3.5 text-subtle transition-transform', open && 'rotate-90')} />
        <span className="flex-1 truncate text-left">{title}</span>
        <span className="num text-[11px] text-subtle">{items.length}</span>
      </button>
      {open && (
        <ul className="pb-1">
          {items.map((item) => {
            const active = item.id === activeId
            return (
              <li key={item.id}>
                <Link
                  to="/stock/$market/$symbol"
                  params={{ market: item.market, symbol: item.symbol }}
                  className={cn(
                    'flex h-7 items-center gap-2 border-l-2 pr-3 pl-[26px] text-[12.5px]',
                    active ? 'border-accent bg-accent-weak text-fg' : 'border-transparent text-muted hover:bg-raised hover:text-fg',
                  )}
                >
                  <span className="flex-1 truncate">{item.name ?? item.symbol}</span>
                  <span className="num text-[11px] text-subtle">{item.symbol.replace(/\.(SZ|SH|BJ)$/, '')}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function Sidebar() {
  const { sidebarOpen, setSidebar } = useUi()
  const universe = useUniverse()
  const watchlist = useWatchlistItems()
  const [cnGroups, otherGroups] = useMemo(() => {
    const groups = universe.data ?? []
    const isCn = (g: (typeof groups)[number]) => g.members.some((m) => m.market === 'CN')
    return [groups.filter(isCn), groups.filter((g) => !isCn(g))]
  }, [universe.data])

  return (
    <>
      {sidebarOpen && <div className="fixed inset-0 z-20 bg-black/30 xl:hidden" onClick={() => setSidebar(false)} aria-hidden />}
      <aside
        aria-label="股票列表"
        className={cn(
          'z-20 w-[228px] shrink-0 overflow-y-auto border-r border-line bg-panel pt-2 pb-6',
          'fixed top-11 bottom-0 left-0 transition-transform xl:sticky xl:top-11 xl:h-[calc(100vh-44px)]',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full xl:hidden',
        )}
      >
        {watchlist.data && watchlist.data.length > 0 && (
          <>
            <SectionTitle>自选</SectionTitle>
            <SidebarGroup title="我的自选" items={watchlist.data} defaultOpen />
          </>
        )}
        <SectionTitle>A股股票池</SectionTitle>
        {universe.isLoading && <div className="px-3 py-2 text-[12px] text-subtle">加载中…</div>}
        {universe.isError && <div className="px-3 py-2 text-[12px] text-warn">股票池加载失败</div>}
        {cnGroups.map((g) => (
          <SidebarGroup key={g.id} title={g.name} items={g.members} defaultOpen={false} />
        ))}
        {otherGroups.length > 0 && <SectionTitle>美股 · 韩股</SectionTitle>}
        {otherGroups.map((g) => (
          <SidebarGroup key={g.id} title={g.name} items={g.members} defaultOpen={false} />
        ))}
      </aside>
    </>
  )
}

function SectionTitle({ children }: { children: string }) {
  return <div className="px-3 pt-3 pb-1 text-[11px] font-medium tracking-wider text-subtle">{children}</div>
}

export function AppShell() {
  const [searchOpen, setSearchOpen] = useState(false)
  useSearchHotkey(setSearchOpen)
  return (
    <div className="min-h-screen">
      <TopBar onSearch={() => setSearchOpen(true)} />
      <div className="flex">
        <Sidebar />
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
      <SearchCommand open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  )
}

/** Global search (Ctrl+K or /). The backend resolves 300308 / SZ300308 / 中际 / AAPL / 005930.KS. */
import * as Dialog from '@radix-ui/react-dialog'
import { useNavigate } from '@tanstack/react-router'
import { Command } from 'cmdk'
import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearch } from '@/api/queries'
import { cn } from '@/lib/utils'
import { Kbd } from './ui'

const MARKET_LABEL = { CN: 'A股', US: '美股', KR: '韩股' } as const

export function useSearchHotkey(setOpen: (open: boolean) => void) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      const typing = target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      if ((event.key === 'k' && (event.ctrlKey || event.metaKey)) || (event.key === '/' && !typing)) {
        event.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [setOpen])
}

export function SearchCommand({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const navigate = useNavigate()
  useEffect(() => {
    const id = setTimeout(() => setDebounced(query), 120)
    return () => clearTimeout(id)
  }, [query])
  const results = useSearch(debounced)

  const go = (market: string, symbol: string) => {
    onOpenChange(false)
    setQuery('')
    navigate({ to: '/stock/$market/$symbol', params: { market, symbol } })
  }

  const items = debounced.trim() ? (results.data ?? []) : []
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]" />
        <Dialog.Content
          className="fixed top-[12vh] left-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-lg border border-line-strong bg-panel shadow-pop"
          aria-describedby={undefined}
        >
          <Dialog.Title className="sr-only">搜索股票</Dialog.Title>
          <Command shouldFilter={false} label="搜索股票" loop>
            <div className="flex items-center gap-2 border-b border-line px-3">
              <Search className="h-4 w-4 text-subtle" aria-hidden />
              <Command.Input
                value={query}
                onValueChange={setQuery}
                placeholder="代码或名称：300308、SZ300308、中际旭创、AAPL、005930.KS"
                className="h-11 flex-1 bg-transparent text-[14px] text-fg outline-none placeholder:text-subtle"
                autoFocus
              />
              <Kbd>Esc</Kbd>
            </div>
            <Command.List className="max-h-[360px] overflow-y-auto p-1.5">
              {debounced.trim() && !results.isFetching && items.length === 0 && (
                <Command.Empty className="px-3 py-8 text-center text-[13px] text-muted">
                  {results.isError ? '搜索服务不可用' : '没有匹配的股票，换一种写法试试'}
                </Command.Empty>
              )}
              {!debounced.trim() && (
                <div className="px-3 py-6 text-center text-[12px] text-subtle">
                  支持 A 股多种写法（300308 / 300308.SZ / SZ300308）、任意美股代码、韩股 .KS / .KQ
                </div>
              )}
              {items.map((item) => (
                <Command.Item
                  key={item.id}
                  value={item.id}
                  onSelect={() => go(item.market, item.symbol)}
                  className={cn(
                    'flex h-9 cursor-pointer items-center gap-3 rounded-md px-2.5 text-[13px]',
                    'data-[selected=true]:bg-raised',
                  )}
                >
                  <span className="w-9 rounded border border-line px-1 text-center text-[10px] text-subtle">{MARKET_LABEL[item.market]}</span>
                  <span className="num w-24 text-fg">{item.symbol}</span>
                  <span className="flex-1 truncate text-muted">{item.name ?? (item.verified ? '' : '按代码打开')}</span>
                  {!item.verified && <span className="text-[11px] text-subtle">未验证</span>}
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

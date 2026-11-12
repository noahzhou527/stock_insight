/** /watchlist — 自选（A 股）: summary, add / remove / undo, searchable sortable table (§6.3, §8 自选). */
import * as Popover from '@radix-ui/react-popover'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import type { ColumnDef, SortingState, VisibilityState } from '@tanstack/react-table'
import { Plus, Search, SlidersHorizontal, Trash2 } from 'lucide-react'
import { useCallback, useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, type Schemas } from '@/api/client'
import { useWatchlistQuotes } from '@/api/queries'
import { PageHeader, QuoteStatusTag, RefreshButton, UndoToast } from '@/components/common'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { DataTable } from '@/components/DataTable'
import { IntradaySparkline } from '@/components/Sparkline'
import { ChangeText, EmptyState, ErrorState } from '@/components/states'
import { Button, Skeleton, Tip } from '@/components/ui'
import { DASH, formatAmount, formatMoneyShort, formatPct, formatPrice, formatRatio, formatSigned, formatTime, isNum } from '@/lib/format'
import { updatePrefs, usePrefs } from '@/lib/prefs'
import { cn } from '@/lib/utils'
import { watchlistRoute } from './router'
import type { Dir, WatchlistSearch, WatchSort } from './search'

type Row = Schemas['WatchlistQuoteRow']

/** Optional columns (§8：开、高、低、振幅、换手率、5 日 / 20 日涨幅、分时迷你走势、停牌标记在名称旁). */
const OPTIONAL: { id: string; label: string }[] = [
  { id: 'open', label: '开盘' },
  { id: 'high', label: '最高' },
  { id: 'low', label: '最低' },
  { id: 'amplitude', label: '振幅' },
  { id: 'turnover', label: '换手率' },
  { id: 'change_5d', label: '5 日涨幅' },
  { id: 'change_20d', label: '20 日涨幅' },
  { id: 'market_cap', label: '总市值' },
  { id: 'pe_ttm', label: 'PE TTM' },
  { id: 'sparkline', label: '分时走势' },
]

const PRESETS: { label: string; sort: WatchSort; dir: Dir }[] = [
  { label: '加入顺序', sort: 'order', dir: 'desc' },
  { label: '涨幅优先', sort: 'change_pct', dir: 'desc' },
  { label: '跌幅优先', sort: 'change_pct', dir: 'asc' },
  { label: '价格从高到低', sort: 'price', dir: 'desc' },
  { label: '成交额从高到低', sort: 'amount', dir: 'desc' },
]

const num = (v: number | null | undefined) => (isNum(v) ? v : undefined) // undefined sorts last in both directions

function splitId(id: string) {
  const [market, symbol] = id.split(':')
  return { market, symbol }
}

function SummaryCell({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  const body = (
    <div className="flex min-w-0 flex-col gap-0.5 px-3 first:pl-4">
      <span className="text-[11px] whitespace-nowrap text-subtle">{label}</span>
      <span className="num text-[14px] whitespace-nowrap">{children}</span>
    </div>
  )
  return hint ? <Tip content={hint}>{body}</Tip> : body
}

function StockLink({ stock }: { stock: Schemas['SummaryStock'] | null | undefined }) {
  if (!stock) return <>{DASH}</>
  const { market, symbol } = splitId(stock.id)
  return (
    <Link to="/stock/$market/$symbol" params={{ market, symbol }} className="hover:underline">
      <span className="text-fg">{stock.name ?? stock.symbol}</span> <ChangeText value={stock.change_pct}>{formatPct(stock.change_pct)}</ChangeText>
    </Link>
  )
}

function Summary({ data }: { data: Schemas['WatchlistQuotesResponse'] }) {
  const s = data.summary
  return (
    <div className="flex overflow-x-auto border-y border-line bg-panel py-2 [scrollbar-width:none]" aria-label="自选汇总">
      <SummaryCell label="自选 / 有效样本" hint="缓存、缺失与旧日期的行情不计入统计">
        {s.total} <span className="text-subtle">/</span> {s.count}
      </SummaryCell>
      <SummaryCell label="等权平均涨跌幅" hint="各股涨跌幅的简单平均，不代表持仓收益">
        <ChangeText value={s.average}>{formatPct(s.average)}</ChangeText>
      </SummaryCell>
      <SummaryCell label="涨 / 跌 / 平">
        <span className="text-up">{s.up}</span> <span className="text-subtle">/</span> <span className="text-down">{s.down}</span> <span className="text-subtle">/</span>{' '}
        <span className="text-flat">{s.flat}</span>
      </SummaryCell>
      <SummaryCell label="领涨">
        <StockLink stock={s.leader} />
      </SummaryCell>
      <SummaryCell label="领跌">
        <StockLink stock={s.laggard} />
      </SummaryCell>
      <SummaryCell label="相对沪深 300" hint={isNum(s.csi300_change_pct) ? `沪深 300 当日 ${formatPct(s.csi300_change_pct)}` : '沪深 300 同日行情暂不可用'}>
        <ChangeText value={s.relative_to_csi300}>{formatSigned(s.relative_to_csi300, 2, ' 个百分点')}</ChangeText>
      </SummaryCell>
    </div>
  )
}

function ColumnChooser({ visible, onChange }: { visible: string[]; onChange: (ids: string[]) => void }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button variant="outline" size="sm" aria-label="显示列">
          <SlidersHorizontal className="h-3.5 w-3.5" /> 列
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={6} className="z-50 w-48 rounded-md border border-line-strong bg-panel p-2 text-[13px] shadow-pop">
          <div className="px-1 pb-1 text-[11px] text-subtle">可选列</div>
          {OPTIONAL.map((col) => {
            const on = visible.includes(col.id)
            return (
              <label key={col.id} className="flex h-7 cursor-pointer items-center gap-2 rounded px-1 hover:bg-raised">
                <input type="checkbox" checked={on} onChange={() => onChange(on ? visible.filter((v) => v !== col.id) : [...visible, col.id])} className="accent-[var(--accent)]" />
                {col.label}
              </label>
            )
          })}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

function AddForm() {
  const client = useQueryClient()
  const [code, setCode] = useState('')
  const add = useMutation({
    mutationFn: (value: string) => api.post<Schemas['WatchlistItem']>('/api/watchlist/items', { code: value }),
    onSuccess: () => {
      setCode('')
      client.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (code.trim()) add.mutate(code.trim())
  }
  const error = add.error instanceof ApiError ? add.error.message : add.error ? String(add.error) : null
  return (
    <form onSubmit={submit} className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <input
          value={code}
          onChange={(e) => {
            setCode(e.target.value)
            if (add.isError) add.reset()
          }}
          placeholder="添加 A 股：300308 / SZ300308 / 300308.SZ"
          aria-label="添加自选代码"
          aria-invalid={Boolean(error)}
          className="num h-7 w-[min(260px,60vw)] rounded-md border border-line bg-panel px-2 text-[13px] text-fg placeholder:text-subtle aria-[invalid=true]:border-error/60"
        />
        <Button type="submit" size="sm" variant="accent" disabled={!code.trim() || add.isPending}>
          <Plus className="h-3.5 w-3.5" /> 加入
        </Button>
      </div>
      {error && (
        <span role="alert" className="text-[12px] text-error">
          {error}
        </span>
      )}
    </form>
  )
}

export function WatchlistPage() {
  const search = watchlistRoute.useSearch() as WatchlistSearch
  const navigate = useNavigate({ from: watchlistRoute.fullPath })
  const client = useQueryClient()
  const query = useWatchlistQuotes()
  const savedColumns = usePrefs((s) => s.prefs.watchlist_columns)
  const visible = useMemo(() => savedColumns ?? [], [savedColumns])
  const [undo, setUndo] = useState<{ removed: Schemas['WatchlistRemoved']; name: string } | null>(null)

  const setSearch = (patch: Partial<WatchlistSearch>, replace = false) => navigate({ search: (prev) => ({ ...prev, ...patch }), replace })
  const setSort = (sort: WatchSort, dir: Dir) => {
    updatePrefs({ watchlist_sort: { sort, dir } })
    setSearch({ sort, dir })
  }

  const remove = useMutation({
    mutationFn: (row: Row) => api.del<Schemas['WatchlistRemoved']>(`/api/watchlist/items/${row.market}/${encodeURIComponent(row.symbol)}`),
    onSuccess: (removed, row) => {
      setUndo({ removed, name: row.name ?? row.symbol })
      client.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })
  const restore = useMutation({
    mutationFn: (removed: Schemas['WatchlistRemoved']) => {
      const { market, symbol } = splitId(removed.id)
      return api.put(`/api/watchlist/items/${market}/${encodeURIComponent(symbol)}`, { sort_order: removed.sort_order, added_at: removed.added_at })
    },
    onSettled: () => client.invalidateQueries({ queryKey: ['watchlist'] }),
  })
  const closeUndo = useCallback(() => setUndo(null), [])
  const removeRow = remove.mutate
  const removing = remove.isPending

  const columns = useMemo<ColumnDef<Row, any>[]>(() => { // eslint-disable-line @typescript-eslint/no-explicit-any
    const price = (id: string, header: string, get: (r: Row) => number | null | undefined): ColumnDef<Row, any> => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
      id,
      header,
      accessorFn: (r) => num(get(r)),
      sortUndefined: 'last',
      meta: { numeric: true },
      cell: ({ getValue }) => formatPrice(getValue(), 'CNY'),
    })
    const pctCol = (id: string, header: string, get: (r: Row) => number | null | undefined, signed = true): ColumnDef<Row, any> => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
      id,
      header,
      accessorFn: (r) => num(get(r)),
      sortUndefined: 'last',
      meta: { numeric: true },
      cell: ({ getValue }) => (signed ? <ChangeText value={getValue()}>{formatPct(getValue())}</ChangeText> : formatRatio(getValue(), 2, '%')),
    })
    return [
      {
        id: 'name',
        header: '名称 / 代码',
        accessorFn: (r) => r.name ?? r.symbol,
        cell: ({ row }) => (
          <span className="inline-flex items-center gap-2">
            <span className="font-medium text-fg">{row.original.name ?? DASH}</span>
            <span className="num text-[12px] text-subtle">{row.original.symbol}</span>
            {row.original.suspended && <span className="rounded border border-warn/40 px-1 text-[10px] text-warn">停牌</span>}
          </span>
        ),
      },
      price('price', '最新价', (r) => r.price),
      pctCol('change_pct', '涨跌幅', (r) => r.change_pct),
      {
        id: 'change',
        header: '涨跌额',
        accessorFn: (r) => num(r.change),
        sortUndefined: 'last',
        meta: { numeric: true },
        cell: ({ getValue }) => <ChangeText value={getValue()}>{formatSigned(getValue(), 2)}</ChangeText>,
      },
      { id: 'amount', header: '成交额', accessorFn: (r) => num(r.amount), sortUndefined: 'last', meta: { numeric: true }, cell: ({ getValue }) => formatAmount(getValue(), 'CN') },
      price('open', '开盘', (r) => r.extra?.open),
      price('high', '最高', (r) => r.extra?.high),
      price('low', '最低', (r) => r.extra?.low),
      pctCol('amplitude', '振幅', (r) => r.extra?.amplitude, false),
      pctCol('turnover', '换手率', (r) => r.extra?.turnover, false),
      pctCol('change_5d', '5 日', (r) => r.change_5d),
      pctCol('change_20d', '20 日', (r) => r.change_20d),
      { id: 'market_cap', header: '总市值', accessorFn: (r) => num(r.market_cap), sortUndefined: 'last', meta: { numeric: true }, cell: ({ getValue }) => formatMoneyShort(getValue(), 'CNY') },
      {
        id: 'pe_ttm',
        header: 'PE TTM',
        accessorFn: (r) => (isNum(r.pe_ttm) && r.pe_ttm > 0 ? r.pe_ttm : undefined),
        sortUndefined: 'last',
        meta: { numeric: true },
        cell: ({ row }) => (isNum(row.original.pe_ttm) ? (row.original.pe_ttm > 0 ? row.original.pe_ttm.toFixed(1) : '亏损') : DASH),
      },
      { id: 'sparkline', header: '分时', enableSorting: false, cell: ({ row }) => <IntradaySparkline market="CN" symbol={row.original.symbol} /> },
      {
        id: 'quote_time',
        header: '行情时间',
        accessorFn: (r) => r.quote_time ?? undefined,
        sortUndefined: 'last',
        meta: { numeric: true },
        cell: ({ row }) => (
          <span className="text-muted">
            {row.original.quote_time ? formatTime(row.original.quote_time, row.original.status === 'old_date') : row.original.trade_date ?? DASH}
          </span>
        ),
      },
      { id: 'status', header: '状态', enableSorting: false, cell: ({ row }) => <QuoteStatusTag status={row.original.status} date={row.original.trade_date} /> },
      {
        id: 'actions',
        header: () => <span className="sr-only">操作</span>,
        enableSorting: false,
        cell: ({ row }) => (
          <Tip content="移出自选">
            <Button
              variant="ghost"
              size="iconSm"
              aria-label={`移出自选：${row.original.name ?? row.original.symbol}`}
              disabled={removing}
              onClick={(e) => {
                e.stopPropagation()
                removeRow(row.original)
              }}
              className="opacity-60 group-hover:opacity-100"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </Tip>
        ),
      },
    ]
  }, [removeRow, removing])

  const columnVisibility = useMemo<VisibilityState>(() => Object.fromEntries(OPTIONAL.map((c) => [c.id, visible.includes(c.id)])), [visible])
  const sorting: SortingState = search.sort === 'order' ? [] : [{ id: search.sort, desc: search.dir === 'desc' }]
  const onSortingChange = (next: SortingState) => (next.length ? setSort(next[0].id as WatchSort, next[0].desc ? 'desc' : 'asc') : setSort('order', 'desc'))

  const q = search.q.trim().toLowerCase()
  const rows = useMemo(
    () => (query.data?.rows ?? []).filter((r) => !q || r.symbol.toLowerCase().includes(q) || (r.name ?? '').toLowerCase().includes(q)),
    [query.data, q],
  )
  const preset = PRESETS.find((p) => p.sort === search.sort && (p.sort === 'order' || p.dir === search.dir))

  return (
    <div data-market="CN" className="min-w-0 pb-10">
      <PageHeader title={query.data?.title ?? '自选'} sub="A 股 · 交易时段每 30 秒更新 · 等权指标不代表持仓收益">
        <DataStatusBadge meta={query.data?.meta} />
        <RefreshButton body={{ target: 'watchlist' }} invalidate={[['watchlist']]} tip="只刷新自选行情" />
      </PageHeader>

      {query.isError && !query.data ? (
        <ErrorState error={query.error} title="自选行情加载失败" onRetry={() => query.refetch()} className="border-y border-line" />
      ) : !query.data ? (
        <div className="flex gap-6 border-y border-line px-4 py-2.5">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-9 w-24" />
          ))}
        </div>
      ) : (
        <Summary data={query.data} />
      )}
      {query.data?.meta.note && <div className="border-b border-warn/30 bg-warn-weak px-4 py-1.5 text-[12px] text-warn">{query.data.meta.note}</div>}

      <div className="flex flex-wrap items-start gap-x-3 gap-y-2 px-4 pt-3 pb-2">
        <AddForm />
        <div className="flex-1" />
        <label className="relative flex items-center">
          <Search className="pointer-events-none absolute left-2 h-3.5 w-3.5 text-subtle" aria-hidden />
          <input
            value={search.q}
            onChange={(e) => setSearch({ q: e.target.value }, true)}
            placeholder="筛选名称或代码"
            aria-label="筛选自选"
            className="h-7 w-44 rounded-md border border-line bg-panel pr-2 pl-7 text-[13px] text-fg placeholder:text-subtle"
          />
        </label>
        <select
          aria-label="排序"
          value={preset ? PRESETS.indexOf(preset) : ''}
          onChange={(e) => {
            const p = PRESETS[Number(e.target.value)]
            if (p) setSort(p.sort, p.dir)
          }}
          className="h-7 cursor-pointer rounded-md border border-line bg-panel px-1.5 text-[13px] text-fg"
        >
          {!preset && <option value="">按表头排序</option>}
          {PRESETS.map((p, i) => (
            <option key={p.label} value={i}>
              {p.label}
            </option>
          ))}
        </select>
        <ColumnChooser visible={visible} onChange={(ids) => updatePrefs({ watchlist_columns: ids })} />
      </div>

      <div className="px-4">
        {query.data && query.data.rows.length === 0 ? (
          <EmptyState title="自选还是空的" hint="在上方输入 A 股代码加入，或在个股页点“自选”" className="rounded-md border border-line bg-panel py-16" />
        ) : !query.data ? (
          <Skeleton className="h-64" />
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            getRowId={(r) => r.id}
            sorting={sorting}
            onSortingChange={onSortingChange}
            columnVisibility={columnVisibility}
            onRowClick={(r) => navigate({ to: '/stock/$market/$symbol', params: { market: r.market, symbol: r.symbol } })}
            height="calc(100vh - 260px)"
            emptyText={`没有匹配“${search.q}”的自选`}
            label="自选行情"
          />
        )}
        <p className={cn('mt-2 text-[12px] text-subtle', !query.data && 'invisible')}>
          行情来源：{query.data?.meta.source ?? DASH} · 缓存、缺失与旧日期的行情不计入汇总统计
        </p>
      </div>

      {undo && (
        <UndoToast
          message={<>已移出自选：{undo.name}</>}
          onUndo={() => {
            restore.mutate(undo.removed)
            setUndo(null)
          }}
          onClose={closeUndo}
        />
      )}
    </div>
  )
}

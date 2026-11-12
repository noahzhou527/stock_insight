/** /rankings — A 股股票池排行 (§6.3, §8 排行). One request for the whole pool; sorting happens here. */
import { useNavigate } from '@tanstack/react-router'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { useMemo } from 'react'
import type { Schemas } from '@/api/client'
import { useRankings } from '@/api/queries'
import { PageHeader, QuoteStatusTag, RefreshButton } from '@/components/common'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { DataTable } from '@/components/DataTable'
import { InfoTip } from '@/components/InfoTip'
import { ChangeText, ErrorState } from '@/components/states'
import { Segmented, Skeleton } from '@/components/ui'
import { DASH, formatAmount, formatMoneyShort, formatPct, formatPrice, formatTime, isNum } from '@/lib/format'
import { rankingsRoute } from './router'
import { metricDir, RANK_METRICS, type Dir, type RankingsSearch, type RankMetric, type RankSort } from './search'

type Row = Schemas['RankingRow']

const METRIC_LABEL: Record<RankMetric, string> = {
  change_pct: '涨跌幅',
  amount: '成交额',
  market_cap: '总市值',
  pe_ttm: 'PE TTM',
  quarter_profit: '季度净利润',
}

/** Invalid values (missing, PE ≤ 0) map to undefined, which always sorts last in either direction. */
function sortValue(row: Row, key: RankSort): number | string | undefined {
  const value = row[key as keyof Row]
  if (key === 'pe_ttm') return isNum(value) && value > 0 ? value : undefined
  if (typeof value === 'string') return value
  return isNum(value) ? value : undefined
}

export function RankingsPage() {
  const search = rankingsRoute.useSearch() as RankingsSearch
  const navigate = useNavigate({ from: rankingsRoute.fullPath })
  const metric = search.metric
  const sortKey: RankSort = search.sort ?? metric
  const dir: Dir = search.dir ?? (search.sort ? 'desc' : metricDir(metric))
  const query = useRankings(metric)

  const columns = useMemo<ColumnDef<Row, any>[]>(() => { // eslint-disable-line @typescript-eslint/no-explicit-any
    const numeric = (id: RankSort, header: React.ReactNode, cell: (row: Row) => React.ReactNode): ColumnDef<Row, any> => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
      id,
      header: () => header,
      accessorFn: (r) => sortValue(r, id),
      sortUndefined: 'last',
      meta: { numeric: true },
      cell: ({ row }) => cell(row.original),
    })
    return [
      {
        id: 'rank',
        header: '#',
        enableSorting: false,
        meta: { width: 44 },
        cell: ({ row, table }) => {
          const position = table.getSortedRowModel().rows.findIndex((r) => r.id === row.id)
          return <span className="num text-subtle">{position + 1}</span>
        },
      },
      {
        id: 'name',
        header: '名称 / 代码',
        accessorFn: (r) => r.name ?? r.symbol,
        cell: ({ row }) => (
          <span className="inline-flex items-center gap-2">
            <span className="font-medium text-fg">{row.original.name ?? DASH}</span>
            <span className="num text-[12px] text-subtle">{row.original.symbol}</span>
          </span>
        ),
      },
      { id: 'group', header: '赛道', accessorFn: (r) => r.group, cell: ({ getValue }) => <span className="text-[12px] text-muted">{getValue()}</span> },
      numeric('price', '最新价', (r) => formatPrice(r.price, 'CNY')),
      numeric('change_pct', '涨跌幅', (r) => <ChangeText value={r.change_pct}>{formatPct(r.change_pct)}</ChangeText>),
      numeric('amount', '成交额', (r) => formatAmount(r.amount, 'CN')),
      numeric('market_cap', '总市值', (r) => formatMoneyShort(r.market_cap, 'CNY')),
      numeric(
        'pe_ttm',
        <span className="inline-flex items-center gap-0.5">
          PE TTM <InfoTip topic="pe" />
        </span>,
        (r) => (isNum(r.pe_ttm) ? (r.pe_ttm > 0 ? r.pe_ttm.toFixed(1) : <span className="text-subtle">亏损/不适用</span>) : DASH),
      ),
      numeric('quarter_profit', '季度净利润', (r) => (
        <span title={r.quarter_period ? `报告期 ${r.quarter_period}（累计口径）` : undefined}>
          {formatMoneyShort(r.quarter_profit, 'CNY')}
          {r.quarter_period && <span className="ml-2 text-[11px] text-subtle">{r.quarter_period.slice(2, 7)}</span>}
        </span>
      )),
      numeric('quarter_profit_yoy', '同比', (r) => <ChangeText value={r.quarter_profit_yoy}>{formatPct(r.quarter_profit_yoy)}</ChangeText>),
      {
        id: 'quote_time',
        header: '行情时间',
        enableSorting: false,
        meta: { numeric: true },
        cell: ({ row }) => <span className="text-muted">{row.original.quote_time ? formatTime(row.original.quote_time, row.original.status === 'old_date') : row.original.trade_date ?? DASH}</span>,
      },
      { id: 'status', header: '状态', enableSorting: false, cell: ({ row }) => <QuoteStatusTag status={row.original.status} date={row.original.trade_date} /> },
    ]
  }, [])

  const sorting: SortingState = [{ id: sortKey, desc: dir === 'desc' }]
  const setSearch = (patch: Partial<RankingsSearch>) => navigate({ search: (prev) => ({ ...prev, ...patch }) })
  const onSortingChange = (next: SortingState) => {
    // A ranking is always sorted: where the table would clear the sort, flip the direction instead.
    if (!next.length) setSearch({ sort: sortKey, dir: dir === 'asc' ? 'desc' : 'asc' })
    else setSearch({ sort: next[0].id as RankSort, dir: next[0].desc ? 'desc' : 'asc' })
  }

  const loadingProfits = metric === 'quarter_profit' && query.isFetching && query.data?.metric !== 'quarter_profit'
  return (
    <div data-market="CN" className="min-w-0 pb-10">
      <PageHeader title="A 股股票池排行" sub={query.data ? `${query.data.rows.length} 只 · 点表头可升降序 · 无效 PE 始终排在最后` : undefined}>
        <DataStatusBadge meta={query.data?.meta} />
        <RefreshButton body={{ target: 'rankings' }} invalidate={[['rankings']]} tip="只刷新排行行情" />
      </PageHeader>
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
        <Segmented
          label="排行指标"
          value={metric}
          onChange={(m) => setSearch({ metric: m, sort: undefined, dir: undefined })}
          options={RANK_METRICS.map((m) => ({ value: m, label: METRIC_LABEL[m] }))}
        />
        {loadingProfits && <span className="text-[12px] text-subtle">正在读取各公司最新季报，首次可能需要半分钟…</span>}
        {query.data?.meta.note && <span className="text-[12px] text-subtle">{query.data.meta.note}</span>}
      </div>
      <div className="px-4">
        {query.isError && !query.data ? (
          <ErrorState error={query.error} title="排行加载失败" onRetry={() => query.refetch()} className="rounded-md border border-line bg-panel" />
        ) : !query.data ? (
          <Skeleton className="h-96" />
        ) : (
          <DataTable
            data={query.data.rows}
            columns={columns}
            getRowId={(r) => r.id}
            sorting={sorting}
            onSortingChange={onSortingChange}
            onRowClick={(r) => navigate({ to: '/stock/$market/$symbol', params: { market: 'CN', symbol: r.symbol } })}
            height="calc(100vh - 190px)"
            label="股票池排行"
          />
        )}
      </div>
    </div>
  )
}

/** 同业对比：仅股票池内 A 股。三种图（营收与净利润 / 净利率 / 资产负债率）+ 明细表。 */
import { useNavigate } from '@tanstack/react-router'
import type { ColumnDef } from '@tanstack/react-table'
import { useMemo, useState } from 'react'
import type { Schemas } from '@/api/client'
import { usePeers } from '@/api/queries'
import { Legend, RankBars } from '@/components/BarChart'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { DataTable } from '@/components/DataTable'
import { EmptyState, ErrorState } from '@/components/states'
import { Segmented, Skeleton } from '@/components/ui'
import { PROFIT_COLOR, REVENUE_COLOR } from '@/charts/chartTheme'
import { DASH, formatMoneyShort, formatRatio, isNum, type Market } from '@/lib/format'

type Peer = Schemas['PeerRow']
type ChartKey = 'scale' | 'margin' | 'debt'

const money = (value: number | null | undefined) => formatMoneyShort(value, 'CNY').replace('¥', '')
const pct = (value: number | null | undefined) => formatRatio(value, 1, '%')

const CHARTS: Record<ChartKey, { label: string; series: { name: string; color: string }[]; values: (p: Peer) => (number | null)[]; format: (v: number) => string }> = {
  scale: {
    label: '营收与净利润',
    series: [
      { name: '营业总收入', color: REVENUE_COLOR },
      { name: '净利润', color: PROFIT_COLOR },
    ],
    values: (p) => [p.revenue, p.net_profit],
    format: money,
  },
  margin: { label: '净利率', series: [{ name: '净利率', color: REVENUE_COLOR }], values: (p) => [p.net_margin], format: pct },
  debt: { label: '资产负债率', series: [{ name: '资产负债率', color: '#f5a524' }], values: (p) => [p.debt_ratio], format: pct },
}

/** Missing values sort last in either direction (TanStack only does that for undefined, not null). */
function numeric(key: 'revenue' | 'net_profit' | 'net_margin' | 'debt_ratio' | 'capex' | 'capex_ratio', header: string, format: (v: number | null | undefined) => string): ColumnDef<Peer, any> { // eslint-disable-line @typescript-eslint/no-explicit-any
  return { id: key, header, accessorFn: (p) => p[key] ?? undefined, meta: { numeric: true }, sortUndefined: 'last', cell: ({ getValue }) => format(getValue()) }
}

export function PeersTab({ market, symbol }: { market: Market; symbol: string }) {
  const query = usePeers(market, symbol)
  const navigate = useNavigate()
  const [chart, setChart] = useState<ChartKey>('scale')
  const open = (peerSymbol: string) => navigate({ to: '/stock/$market/$symbol', params: { market: 'CN', symbol: peerSymbol } })

  const columns = useMemo<ColumnDef<Peer, any>[]>( // eslint-disable-line @typescript-eslint/no-explicit-any
    () => [
      {
        id: 'name',
        header: '名称 / 代码',
        accessorFn: (p) => p.name ?? p.symbol,
        cell: ({ row }) => (
          <span className="inline-flex items-center gap-2">
            <span className={row.original.symbol === symbol ? 'font-semibold text-accent' : 'text-fg'}>{row.original.name ?? DASH}</span>
            <span className="num text-[12px] text-subtle">{row.original.symbol}</span>
          </span>
        ),
      },
      { accessorKey: 'period_end', header: '报告期', cell: ({ getValue }) => <span className="num text-muted">{getValue() ?? DASH}</span> },
      numeric('revenue', '营业总收入', money),
      numeric('net_profit', '净利润', money),
      numeric('net_margin', '净利率', pct),
      numeric('debt_ratio', '资产负债率', pct),
      numeric('capex', '资本开支', money),
      numeric('capex_ratio', '资本开支 / 营收', pct),
    ],
    [symbol],
  )

  if (query.isError && !query.data) return <ErrorState error={query.error} title="同业对比加载失败" onRetry={() => query.refetch()} />
  if (!query.data) {
    return (
      <div className="space-y-2 p-4">
        <p className="text-[12px] text-subtle">正在读取同赛道各公司的最新年报，首次加载可能需要十几秒…</p>
        <Skeleton className="h-64" />
      </div>
    )
  }
  const { supported, message, group, rows, meta } = query.data
  if (!supported) return <EmptyState title="暂不支持同业对比" hint={message ?? '暂只支持股票池内 A 股的同赛道对比'} className="py-14" />

  const spec = CHARTS[chart]
  const ranked = rows
    .map((p) => ({ id: p.symbol, label: p.name ?? p.symbol, values: spec.values(p), highlight: p.symbol === symbol }))
    .sort((a, b) => (isNum(b.values[0]) ? b.values[0] : -Infinity) - (isNum(a.values[0]) ? a.values[0] : -Infinity))
  return (
    <section className="space-y-3 p-4" aria-label="同业对比">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="text-[14px] font-semibold">同赛道对比 · {group}</h2>
        <span className="text-[12px] text-subtle">{rows.length} 家，最新年报口径</span>
        <div className="flex-1" />
        <DataStatusBadge meta={meta} compact />
      </header>
      <div className="rounded-md border border-line bg-panel p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <Segmented label="对比图" value={chart} onChange={setChart} options={(Object.keys(CHARTS) as ChartKey[]).map((k) => ({ value: k, label: CHARTS[k].label }))} />
          <Legend series={spec.series} />
        </div>
        <RankBars rows={ranked} series={spec.series} format={spec.format} onRowClick={open} label={`${spec.label}对比`} />
      </div>
      <DataTable data={rows} columns={columns} getRowId={(p) => p.id} onRowClick={(p) => open(p.symbol)} height={520} label="同业对比明细" />
      {meta.note && <p className="text-[12px] text-subtle">{meta.note}</p>}
    </section>
  )
}

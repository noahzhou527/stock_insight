/** 数据明细：最近 N 行日线 + 统计摘要 + CSV 导出（所选区间）。Reuses the bars already loaded for the chart. */
import type { ColumnDef } from '@tanstack/react-table'
import { Download } from 'lucide-react'
import { useMemo, useState } from 'react'
import { instrumentPath, type Schemas } from '@/api/client'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { DataTable } from '@/components/DataTable'
import { ChangeText, EmptyState } from '@/components/states'
import { Segmented, Tip } from '@/components/ui'
import { DASH, formatAmount, formatPct, formatPrice, formatRatio, formatVolume, isNum, type Market } from '@/lib/format'
import { describe, DESCRIBE_ROWS, type Describe } from '@/lib/stats'

type Bar = Schemas['Bar']
interface Row extends Bar {
  change_pct: number | null
  rsi: number | null
}

const ROW_CHOICES = ['20', '60', '120', 'all'] as const
type RowChoice = (typeof ROW_CHOICES)[number]

export function DataTab({
  data,
  market,
  symbol,
  currency,
  apiCurrency,
  rsiPeriod,
  start,
  end,
}: {
  data: Schemas['BarsResponse']
  market: Market
  symbol: string
  currency: string
  apiCurrency?: string
  rsiPeriod: number
  start: string
  end?: string
}) {
  const [choice, setChoice] = useState<RowChoice>('20')
  const rsiValues = data.indicators[`rsi${rsiPeriod}`]
  const all = useMemo<Row[]>(
    () =>
      data.bars
        .map((bar, i) => {
          const prev = data.bars[i - 1]
          return {
            ...bar,
            change_pct: prev && isNum(bar.close) && isNum(prev.close) && prev.close !== 0 ? (bar.close / prev.close - 1) * 100 : null,
            rsi: rsiValues?.[i] ?? null,
          }
        })
        .reverse(),
    [data.bars, rsiValues],
  )
  const rows = choice === 'all' ? all : all.slice(0, Number(choice))

  const columns = useMemo<ColumnDef<Row, any>[]>( // eslint-disable-line @typescript-eslint/no-explicit-any
    () => {
      const price = (key: 'open' | 'high' | 'low' | 'close', header: string): ColumnDef<Row, any> => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
        accessorKey: key,
        header,
        meta: { numeric: true },
        cell: ({ getValue }) => formatPrice(getValue(), currency),
      })
      return [
        {
          accessorKey: 'date',
          header: '日期',
          cell: ({ row }) => (
            <span className="num inline-flex items-center gap-1.5">
              {row.original.date}
              {row.original.provisional && <span className="rounded border border-accent/30 px-1 text-[10px] text-accent">盘中合成</span>}
            </span>
          ),
        },
        price('open', '开盘'),
        price('high', '最高'),
        price('low', '最低'),
        price('close', '收盘'),
        {
          id: 'change_pct',
          accessorFn: (r) => r.change_pct ?? undefined,
          header: '涨跌幅',
          meta: { numeric: true },
          sortUndefined: 'last',
          cell: ({ getValue }) => <ChangeText value={getValue()}>{formatPct(getValue())}</ChangeText>,
        },
        { accessorKey: 'volume', header: '成交量', meta: { numeric: true }, cell: ({ getValue }) => formatVolume(getValue(), market) },
        {
          accessorKey: 'amount',
          header: '成交额',
          meta: { numeric: true },
          cell: ({ row }) => (
            <span>
              {formatAmount(row.original.amount, market, currency)}
              {row.original.amount_estimated && (
                <Tip content="成交额为 收盘价 × 成交量 估算">
                  <span className="ml-1 text-[10px] text-subtle">估</span>
                </Tip>
              )}
            </span>
          ),
        },
        { accessorKey: 'rsi', header: `RSI(${rsiPeriod})`, meta: { numeric: true }, cell: ({ getValue }) => formatRatio(getValue(), 1) },
        { accessorKey: 'source', header: '来源', enableSorting: false, cell: ({ getValue }) => <span className="text-[12px] text-subtle">{getValue()}</span> },
      ]
    },
    [currency, market, rsiPeriod],
  )

  const stats = useMemo(() => {
    const column = (key: 'open' | 'high' | 'low' | 'close' | 'volume' | 'amount') => describe(data.bars.map((b) => b[key]))
    return { open: column('open'), high: column('high'), low: column('low'), close: column('close'), volume: column('volume'), amount: column('amount') }
  }, [data.bars])

  if (data.bars.length === 0) return <EmptyState title="所选区间没有日线数据" className="py-14" />

  const csvQuery = new URLSearchParams({ start, ...(end ? { end } : {}), ...(apiCurrency ? { currency: apiCurrency } : {}) })
  const statCell = (d: Describe | null, key: (typeof DESCRIBE_ROWS)[number]['key'], kind: 'price' | 'volume' | 'amount') => {
    const value = d?.[key]
    if (!isNum(value)) return DASH
    return kind === 'price' ? formatPrice(value, currency) : kind === 'volume' ? formatVolume(value, market) : formatAmount(value, market, currency)
  }
  return (
    <section className="space-y-4 p-4" aria-label="数据明细">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="text-[14px] font-semibold">日线明细</h2>
        <span className="num text-[12px] text-subtle">
          {data.bars[0].date} 至 {data.bars[data.bars.length - 1].date}，共 {data.bars.length} 个交易日
        </span>
        <div className="flex-1" />
        <DataStatusBadge meta={data.meta} compact />
        <Segmented
          label="显示行数"
          value={choice}
          onChange={setChoice}
          options={ROW_CHOICES.map((c) => ({ value: c, label: c === 'all' ? '全部' : `近 ${c} 行`, disabled: c !== 'all' && c !== '20' && Number(c) > all.length }))}
        />
        <a
          href={`${instrumentPath(market, symbol, '/bars.csv')}?${csvQuery}`}
          download
          className="inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-raised px-2.5 text-[13px] font-medium text-fg hover:bg-line-strong/60"
        >
          <Download className="h-3.5 w-3.5" /> 导出 CSV
        </a>
      </header>
      <DataTable data={rows} columns={columns} getRowId={(r) => r.date} height={560} rowHeight={32} label="日线明细" />

      <div>
        <h3 className="mb-1.5 text-[13px] font-semibold">
          统计摘要 <span className="num ml-1 text-[12px] font-normal text-subtle">所选区间 {data.bars.length} 个交易日</span>
        </h3>
        <div className="overflow-x-auto rounded-md border border-line bg-panel">
          <table className="w-full border-separate border-spacing-0 text-[13px]" aria-label="统计摘要">
            <thead>
              <tr>
                {['统计项', '开盘', '最高', '最低', '收盘', '成交量', '成交额'].map((h, i) => (
                  <th key={h} scope="col" className={`h-8 border-b border-line px-3 text-[12px] font-medium whitespace-nowrap text-subtle ${i ? 'text-right' : 'sticky left-0 bg-panel text-left'}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DESCRIBE_ROWS.map(({ key, label }) => (
                <tr key={key} className="group">
                  <th scope="row" className="sticky left-0 h-8 border-b border-line bg-panel px-3 text-left font-normal whitespace-nowrap text-muted group-last:border-b-0">
                    {label}
                  </th>
                  {(['open', 'high', 'low', 'close'] as const).map((c) => (
                    <td key={c} className="num border-b border-line px-3 text-right whitespace-nowrap group-last:border-b-0">
                      {statCell(stats[c], key, 'price')}
                    </td>
                  ))}
                  <td className="num border-b border-line px-3 text-right whitespace-nowrap group-last:border-b-0">{statCell(stats.volume, key, 'volume')}</td>
                  <td className="num border-b border-line px-3 text-right whitespace-nowrap group-last:border-b-0">{statCell(stats.amount, key, 'amount')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

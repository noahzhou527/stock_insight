/** 财务报表：近 4 个财年 + 近 4 个季度的表格；A 股另有年报图和季度图（季度图用年报补齐第四季度）。 */
import { useFinancials } from '@/api/queries'
import { GroupedBars } from '@/components/BarChart'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { ChangeText, EmptyState, ErrorState } from '@/components/states'
import { Skeleton } from '@/components/ui'
import { PROFIT_COLOR, REVENUE_COLOR } from '@/charts/chartTheme'
import { METRICS, pivotReports, quarterChartPeriods, reportTypeLabel, type MetricKind, type ReportPeriod } from '@/lib/financials'
import { currencySymbol, DASH, formatMoneyShort, formatPct, formatRatio, isNum, type Market } from '@/lib/format'

function formatMetric(value: number | null | undefined, kind: MetricKind, currency: string) {
  if (!isNum(value)) return DASH
  if (kind === 'amount') return formatMoneyShort(value, currency)
  if (kind === 'per_share') return `${currencySymbol(currency)}${value.toFixed(currency === 'KRW' ? 0 : 2)}`
  if (kind === 'yoy') return <ChangeText value={value}>{formatPct(value)}</ChangeText>
  return formatRatio(value, 2, '%')
}

/** Chart labels without the currency symbol: 12.3亿 / 4.5B */
const barLabel = (currency: string) => (value: number) => formatMoneyShort(value, currency).replace(/^[¥$₩]/, '')

function periodLabel(period: ReportPeriod, market: Market) {
  if (market !== 'CN') return period.period_end.slice(0, 7)
  const year = period.period_end.slice(0, 4)
  return period.report_type === 'annual' ? `${year} 年报` : `${year.slice(2)} ${reportTypeLabel(period.report_type)}`
}

function ReportTable({ title, periods, currency, market }: { title: string; periods: ReportPeriod[]; currency: string; market: Market }) {
  const metrics = METRICS.filter((m) => periods.some((p) => isNum(p.values[m.key])))
  return (
    <div className="min-w-0">
      <h3 className="mb-1.5 text-[13px] font-semibold">{title}</h3>
      {periods.length === 0 ? (
        <EmptyState title="暂未读取到可展示的报告" className="rounded-md border border-line bg-panel" />
      ) : (
        <div className="overflow-x-auto rounded-md border border-line bg-panel">
          <table className="w-full border-separate border-spacing-0 text-[13px]">
            <thead>
              <tr>
                <th scope="col" className="sticky left-0 h-9 border-b border-line bg-panel px-3 text-left text-[12px] font-medium text-subtle">
                  指标
                </th>
                {periods.map((p) => (
                  <th key={p.period_end} scope="col" className="num h-9 border-b border-line px-3 text-right text-[12px] font-medium whitespace-nowrap text-subtle">
                    {p.period_end}
                    {market === 'CN' && <span className="ml-1 text-[11px]">{reportTypeLabel(p.report_type)}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.key} className="group">
                  <th scope="row" className="sticky left-0 h-8 border-b border-line bg-panel px-3 text-left font-normal whitespace-nowrap text-muted group-last:border-b-0">
                    {m.label}
                  </th>
                  {periods.map((p) => (
                    <td key={p.period_end} className="num h-8 border-b border-line px-3 text-right whitespace-nowrap group-last:border-b-0">
                      {formatMetric(p.values[m.key], m.kind, currency)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function FinancialsTab({ market, symbol, currency, apiCurrency }: { market: Market; symbol: string; currency: string; apiCurrency?: string }) {
  const query = useFinancials(market, symbol, apiCurrency)
  if (query.isError && !query.data) return <ErrorState error={query.error} title="财报加载失败" onRetry={() => query.refetch()} />
  if (!query.data) {
    return (
      <div className="grid gap-3 p-4 lg:grid-cols-2">
        <Skeleton className="h-56" />
        <Skeleton className="h-56" />
      </div>
    )
  }
  const { rows, annual_periods, quarterly_periods, fx, meta } = query.data
  const annual = pivotReports(rows, annual_periods, 'annual')
  const quarters = pivotReports(rows, quarterly_periods, 'interim')
  if (annual.length === 0 && quarters.length === 0) return <EmptyState title="暂无财报数据" hint={meta.note ?? undefined} className="py-14" />

  const chartAnnual = [...annual].reverse()
  const chartQuarters = quarterChartPeriods(quarters, annual, market === 'CN')
  const filled = chartQuarters.length > quarters.length
  const bars = (periods: ReportPeriod[]) => [
    { name: '营业总收入', color: REVENUE_COLOR, values: periods.map((p) => p.values.revenue) },
    { name: '净利润', color: PROFIT_COLOR, values: periods.map((p) => p.values.net_profit) },
  ]
  return (
    <section className="space-y-4 p-4" aria-label="财务报表">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-[14px] font-semibold">年度与季度财务报告</h2>
        <span className="text-[12px] text-subtle">
          {fx
            ? `金额与每股收益按参考汇率换算为 ${fx.to}（1 ${fx.from} = ${fx.rate.toPrecision(4)} ${fx.to}）`
            : market === 'CN'
              ? 'A 股季报为报告期累计口径（一季报、中报、三季报），未拆分单季'
              : '金额按报告币种展示'}
        </span>
        <div className="flex-1" />
        <DataStatusBadge meta={meta} compact />
      </header>

      {market === 'CN' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-md border border-line bg-panel p-3">
            {chartAnnual.length ? (
              <GroupedBars title="年报：营收与净利润" categories={chartAnnual.map((p) => periodLabel(p, market))} series={bars(chartAnnual)} format={barLabel(currency)} />
            ) : (
              <EmptyState title="暂无年报" />
            )}
          </div>
          <div className="rounded-md border border-line bg-panel p-3">
            {chartQuarters.length ? (
              <>
                <GroupedBars title="季报趋势（累计口径）" categories={chartQuarters.map((p) => periodLabel(p, market))} series={bars(chartQuarters)} format={barLabel(currency)} />
                {filled && <p className="mt-1 text-[11px] text-subtle">季度图以年报补齐缺失的第四季度；下方季度表不受影响。</p>}
              </>
            ) : (
              <EmptyState title="暂无季报" />
            )}
          </div>
        </div>
      )}

      <div className="grid gap-4 2xl:grid-cols-2">
        <ReportTable title={annual.length ? `近 ${annual.length} 个财年` : '财年报告'} periods={annual} currency={currency} market={market} />
        <ReportTable title={quarters.length ? `最新 ${quarters.length} 个季度` : '季度报告'} periods={quarters} currency={currency} market={market} />
      </div>
    </section>
  )
}

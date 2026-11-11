/** Reshape the long financial-report rows (period × metric) for tables and charts. */
import type { Schemas } from '@/api/client'

type Row = Schemas['ReportRowOut']

export interface ReportPeriod {
  period_end: string
  report_type: Row['report_type']
  values: Record<string, number | null>
}

export type MetricKind = 'amount' | 'pct' | 'yoy' | 'per_share'

/** Display order. Only metrics that have at least one value are shown. */
export const METRICS: { key: string; label: string; kind: MetricKind }[] = [
  { key: 'revenue', label: '营业总收入', kind: 'amount' },
  { key: 'revenue_yoy', label: '营收同比', kind: 'yoy' },
  { key: 'gross_profit', label: '毛利润', kind: 'amount' },
  { key: 'operating_income', label: '营业利润', kind: 'amount' },
  { key: 'net_profit', label: '净利润', kind: 'amount' },
  { key: 'net_profit_yoy', label: '净利润同比', kind: 'yoy' },
  { key: 'net_profit_excl', label: '扣非净利润', kind: 'amount' },
  { key: 'gross_margin', label: '销售毛利率', kind: 'pct' },
  { key: 'roe', label: '净资产收益率', kind: 'pct' },
  { key: 'debt_ratio', label: '资产负债率', kind: 'pct' },
  { key: 'eps_basic', label: '基本每股收益', kind: 'per_share' },
  { key: 'ocf_per_share', label: '每股经营现金流', kind: 'per_share' },
  { key: 'capex', label: '资本开支', kind: 'amount' },
]

const TYPE_LABEL: Record<Row['report_type'], string> = { annual: '年报', q1: '一季报', h1: '中报', q3: '三季报', quarterly: '单季' }

export function reportTypeLabel(type: Row['report_type']): string {
  return TYPE_LABEL[type]
}

/**
 * One entry per period, newest first. A period end can carry both an annual and a quarterly report
 * (美股财年末), so rows are split by report type, not by date alone.
 */
export function pivotReports(rows: Row[], periods: string[], kind: 'annual' | 'interim'): ReportPeriod[] {
  const wanted = (row: Row) => (kind === 'annual' ? row.report_type === 'annual' : row.report_type !== 'annual')
  const byPeriod = new Map<string, ReportPeriod>()
  for (const row of rows) {
    if (!wanted(row) || !periods.includes(row.period_end)) continue
    let period = byPeriod.get(row.period_end)
    if (!period) {
      period = { period_end: row.period_end, report_type: row.report_type, values: {} }
      byPeriod.set(row.period_end, period)
    }
    period.values[row.metric] = row.value
  }
  return [...byPeriod.values()].sort((a, b) => b.period_end.localeCompare(a.period_end))
}

/**
 * 季度图：A 股季报没有第四季度（年报即全年累计），用落在季度区间内的年报补齐，
 * 使横轴连续。只影响图，不影响季度表。Returns oldest → newest.
 */
export function quarterChartPeriods(quarters: ReportPeriod[], annuals: ReportPeriod[], fillWithAnnual: boolean): ReportPeriod[] {
  if (quarters.length === 0) return []
  const dates = quarters.map((q) => q.period_end).sort()
  const fill = fillWithAnnual
    ? annuals.filter((a) => a.period_end >= dates[0] && a.period_end <= dates[dates.length - 1] && !dates.includes(a.period_end))
    : []
  return [...quarters, ...fill].sort((a, b) => a.period_end.localeCompare(b.period_end))
}

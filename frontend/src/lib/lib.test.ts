import { describe as suite, expect, it } from 'vitest'
import type { Schemas } from '@/api/client'
import { pivotReports, quarterChartPeriods } from './financials'
import { describe } from './stats'

type Row = Schemas['ReportRowOut']
const row = (period_end: string, report_type: Row['report_type'], metric: string, value: number | null): Row => ({ period_end, report_type, metric, value, currency: 'CNY' })

suite('describe', () => {
  it('matches pandas describe() for [1, 2, 3, 4, 10]', () => {
    const d = describe([1, 2, null, 3, 4, 10, undefined])!
    expect(d.count).toBe(5)
    expect(d.mean).toBe(4)
    expect(d.std).toBeCloseTo(3.5355339, 6)
    expect([d.min, d.q25, d.median, d.q75, d.max]).toEqual([1, 2, 3, 4, 10])
  })

  it('interpolates quantiles and handles tiny samples', () => {
    expect(describe([1, 2, 3, 4])!.q25).toBeCloseTo(1.75)
    expect(describe([5])).toMatchObject({ count: 1, mean: 5, std: null, min: 5, max: 5 })
    expect(describe([null, undefined])).toBeNull()
  })
})

suite('financial report reshaping', () => {
  const rows = [
    row('2026-09-30', 'q3', 'revenue', 30),
    row('2026-06-30', 'h1', 'revenue', 20),
    row('2026-03-31', 'q1', 'revenue', 10),
    row('2025-12-31', 'annual', 'revenue', 40),
    row('2025-12-31', 'annual', 'net_profit', 8),
    row('2025-09-30', 'q3', 'revenue', 28),
    row('2024-12-31', 'annual', 'revenue', 35),
  ]
  const annual = pivotReports(rows, ['2025-12-31', '2024-12-31'], 'annual')
  const quarters = pivotReports(rows, ['2026-09-30', '2026-06-30', '2026-03-31', '2025-09-30'], 'interim')

  it('pivots newest first and merges metrics of one period', () => {
    expect(annual.map((p) => p.period_end)).toEqual(['2025-12-31', '2024-12-31'])
    expect(annual[0].values).toEqual({ revenue: 40, net_profit: 8 })
    expect(quarters.map((p) => p.report_type)).toEqual(['q3', 'h1', 'q1', 'q3'])
  })

  it('fills the missing fourth quarter of the chart from the annual report (A 股)', () => {
    const chart = quarterChartPeriods(quarters, annual, true)
    expect(chart.map((p) => p.period_end)).toEqual(['2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30', '2026-09-30'])
    expect(quarterChartPeriods(quarters, annual, false)).toHaveLength(4)
  })

  it('keeps annual and quarterly reports that share a period end apart (美股财年末)', () => {
    const us = [row('2025-09-27', 'annual', 'revenue', 400), row('2025-09-27', 'quarterly', 'revenue', 100)]
    expect(pivotReports(us, ['2025-09-27'], 'annual')[0].values.revenue).toBe(400)
    expect(pivotReports(us, ['2025-09-27'], 'interim')[0].values.revenue).toBe(100)
  })
})

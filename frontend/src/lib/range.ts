/** Date ranges expressed as URL presets (range=1y), resolved against the market's "today". */
export const RANGES = ['1m', '3m', '6m', '1y', 'ytd', 'custom'] as const
export type RangeKey = (typeof RANGES)[number]

export const RANGE_LABELS: Record<RangeKey, string> = {
  '1m': '1月',
  '3m': '3月',
  '6m': '6月',
  '1y': '1年',
  ytd: '今年',
  custom: '自定义',
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

function parse(day: string): Date {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function monthsBefore(day: string, months: number): string {
  const d = parse(day)
  const target = new Date(d.getFullYear(), d.getMonth() - months, 1)
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()
  target.setDate(Math.min(d.getDate(), lastDay))
  return iso(target)
}

/** Returns the display range. ``today`` is the market-local date from /api/market/sessions. */
export function resolveRange(range: RangeKey, today: string, start?: string, end?: string): { start: string; end?: string } {
  switch (range) {
    case '1m':
      return { start: monthsBefore(today, 1) }
    case '3m':
      return { start: monthsBefore(today, 3) }
    case '6m':
      return { start: monthsBefore(today, 6) }
    case 'ytd':
      return { start: `${today.slice(0, 4)}-01-01` }
    case 'custom':
      return { start: start ?? monthsBefore(today, 12), end: end || undefined }
    default:
      return { start: monthsBefore(today, 12) }
  }
}

export function localToday(): string {
  return iso(new Date())
}

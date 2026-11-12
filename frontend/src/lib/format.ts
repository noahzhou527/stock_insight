/**
 * Number formatting — same rules as backend/app/domain/format.py (and legacy formatters.py):
 * A 股 / 韩股 用 万 / 亿 / 万亿，美股用 K / M / B / T，空值显示 "—"。
 * Shared cases are tested on both sides (format.test.ts ↔ backend tests/test_domain.py).
 */
export type Market = 'CN' | 'US' | 'KR'

export const DASH = '—'

export function isNum(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function compact(value: number | null | undefined, tiers: [number, string][], suffix: string): string {
  if (!isNum(value)) return DASH
  for (const [divisor, unit] of tiers) {
    if (Math.abs(value) >= divisor) return `${(value / divisor).toFixed(2)}${unit}`
  }
  return `${Math.round(value).toLocaleString('en-US')}${suffix}`
}

export function formatVolume(value: number | null | undefined, market: Market = 'CN'): string {
  if (market === 'CN') return compact(value, [[1e8, '亿股'], [1e4, '万股']], '股')
  return compact(value, [[1e9, 'B股'], [1e6, 'M股'], [1e3, 'K股']], '股')
}

export function formatAmount(value: number | null | undefined, market: Market = 'CN', currency?: string): string {
  if (currency === 'USD' && market !== 'US') market = 'US' // 韩股换算为美元时按美元习惯显示
  if (market === 'CN') return compact(value, [[1e12, '万亿元'], [1e8, '亿元'], [1e4, '万元']], '元')
  if (market === 'KR') return compact(value, [[1e12, '万亿韩元'], [1e8, '亿韩元'], [1e4, '万韩元']], '韩元')
  return compact(value, [[1e12, 'T美元'], [1e9, 'B美元'], [1e6, 'M美元'], [1e3, 'K美元']], '美元')
}

/** Short amount without currency word, for dense attribute cells: ¥12.34亿 / $3.20B / ₩1.20万亿 */
export function formatMoneyShort(value: number | null | undefined, currency: string): string {
  if (!isNum(value)) return DASH
  const symbol = currencySymbol(currency)
  if (currency === 'USD') {
    const tiers: [number, string][] = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']]
    for (const [d, u] of tiers) if (Math.abs(value) >= d) return `${symbol}${(value / d).toFixed(2)}${u}`
    return `${symbol}${value.toFixed(0)}`
  }
  const tiers: [number, string][] = [[1e12, '万亿'], [1e8, '亿'], [1e4, '万']]
  for (const [d, u] of tiers) if (Math.abs(value) >= d) return `${symbol}${(value / d).toFixed(2)}${u}`
  return `${symbol}${value.toFixed(0)}`
}

export function currencySymbol(currency: string | null | undefined): string {
  return currency === 'USD' ? '$' : currency === 'KRW' ? '₩' : '¥'
}

/** Prices: KRW has no minor unit in practice; everything else 2 decimals (3 for sub-1 prices). */
export function formatPrice(value: number | null | undefined, currency?: string | null): string {
  if (!isNum(value)) return DASH
  if (currency === 'KRW') return Math.round(value).toLocaleString('en-US')
  const digits = Math.abs(value) < 1 ? 3 : 2
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** Signed change: +1.23 / −1.23 (U+2212 for alignment and accessibility). */
export function formatSigned(value: number | null | undefined, digits = 2, suffix = ''): string {
  if (!isNum(value)) return DASH
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${Math.abs(value).toFixed(digits)}${suffix}`
}

export function formatPct(value: number | null | undefined, digits = 2): string {
  return formatSigned(value, digits, '%')
}

export function formatRatio(value: number | null | undefined, digits = 2, suffix = ''): string {
  return isNum(value) ? `${value.toFixed(digits)}${suffix}` : DASH
}

export function trendOf(value: number | null | undefined): 'up' | 'down' | 'flat' {
  if (!isNum(value) || value === 0) return 'flat'
  return value > 0 ? 'up' : 'down'
}

const pad = (n: number) => String(n).padStart(2, '0')

export function formatTime(value: string | Date | null | undefined, withDate = false): string {
  if (!value) return DASH
  const d = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(d.getTime())) return DASH
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  return withDate ? `${d.getMonth() + 1}-${pad(d.getDate())} ${time}` : time
}

/** News times: "14:05" today, "昨天 14:05", else "11-10 14:05" (local time). */
export function formatRelativeTime(value: string, now = new Date()): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return DASH
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((day(now) - day(d)) / 86_400_000)
  if (diff === 0) return time
  if (diff === 1) return `昨天 ${time}`
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${time}`
}

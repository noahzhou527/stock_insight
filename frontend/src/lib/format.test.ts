import { describe, expect, it } from 'vitest'
import { formatAmount, formatMoneyShort, formatPct, formatPrice, formatSigned, formatVolume, trendOf } from './format'

// Same cases as backend/tests/test_domain.py::test_format_volume / test_format_amount.
describe('shared formatting cases (backend parity)', () => {
  it.each([
    [15000, 'CN', '1.50万股'],
    [1.5e8, 'CN', '1.50亿股'],
    [2.5e6, 'US', '2.50M股'],
    [null, 'CN', '—'],
  ] as const)('formatVolume(%s, %s) = %s', (value, market, expected) => {
    expect(formatVolume(value, market)).toBe(expected)
  })

  it.each([
    [1.5e8, 'CN', '1.50亿元'],
    [2e12, 'KR', '2.00万亿韩元'],
    [3.2e9, 'US', '3.20B美元'],
    [Number.NaN, 'US', '—'],
    [999, 'CN', '999元'],
  ] as const)('formatAmount(%s, %s) = %s', (value, market, expected) => {
    expect(formatAmount(value, market)).toBe(expected)
  })
})

describe('display helpers', () => {
  it('signs with a real minus sign', () => {
    expect(formatSigned(1.234)).toBe('+1.23')
    expect(formatSigned(-1.234)).toBe('−1.23')
    expect(formatSigned(0)).toBe('0.00')
    expect(formatPct(15.0743)).toBe('+15.07%')
  })

  it('formats prices per currency', () => {
    expect(formatPrice(542)).toBe('542.00')
    expect(formatPrice(0.4567)).toBe('0.457')
    expect(formatPrice(70500.4, 'KRW')).toBe('70,500')
    expect(formatPrice(null)).toBe('—')
  })

  it('short money', () => {
    expect(formatMoneyShort(6.384e11, 'CNY')).toBe('¥6384.00亿')
    expect(formatMoneyShort(3.2e12, 'USD')).toBe('$3.20T')
    expect(formatMoneyShort(1.2e14, 'KRW')).toBe('₩120.00万亿')
  })

  it('trend', () => {
    expect(trendOf(1)).toBe('up')
    expect(trendOf(-0.1)).toBe('down')
    expect(trendOf(0)).toBe('flat')
    expect(trendOf(null)).toBe('flat')
  })
})

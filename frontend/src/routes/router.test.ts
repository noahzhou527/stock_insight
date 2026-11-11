import { describe, expect, it } from 'vitest'
import { parseMa, validateStockSearch } from './router'

describe('stock search params', () => {
  it('fills defaults', () => {
    expect(validateStockSearch({})).toEqual({ range: '1y', start: undefined, end: undefined, ma: '5,10,20', bbi: false, boll: false, rsi: 14, sub: 'volume', chart: 'kline', cur: 'KRW', tab: 'signals' })
  })

  it('keeps valid values and drops malformed ones', () => {
    const search = validateStockSearch({ range: 'ytd', start: '2026-01-05', end: 'bad', ma: '20,5,x,5,999', bbi: 'true', boll: 1, rsi: 9, sub: 'macd', chart: 'intraday', cur: 'USD', tab: 'peers' })
    expect(search).toEqual({ range: 'ytd', start: '2026-01-05', end: undefined, ma: '5,20', bbi: true, boll: true, rsi: 9, sub: 'macd', chart: 'intraday', cur: 'USD', tab: 'peers' })
    expect(validateStockSearch({ range: 'forever' }).range).toBe('1y')
    expect(validateStockSearch({ rsi: 40, sub: 'kdj', tab: 'x' })).toMatchObject({ rsi: 14, sub: 'volume', tab: 'signals' })
  })

  it('allows an empty MA selection', () => {
    expect(validateStockSearch({ ma: '' }).ma).toBe('')
    expect(parseMa('')).toEqual([])
  })
})

import { describe, expect, it } from 'vitest'
import { parseMa, validateStockSearch } from './router'

describe('stock search params', () => {
  it('fills defaults', () => {
    expect(validateStockSearch({})).toEqual({ range: '1y', start: undefined, end: undefined, ma: '5,10,20', sub: 'volume', chart: 'kline', cur: 'KRW' })
  })

  it('keeps valid values and drops malformed ones', () => {
    const search = validateStockSearch({ range: 'ytd', start: '2026-01-05', end: 'bad', ma: '20,5,x,5,999', sub: 'amount', chart: 'intraday', cur: 'USD' })
    expect(search).toEqual({ range: 'ytd', start: '2026-01-05', end: undefined, ma: '5,20', sub: 'amount', chart: 'intraday', cur: 'USD' })
    expect(validateStockSearch({ range: 'forever' }).range).toBe('1y')
  })

  it('allows an empty MA selection', () => {
    expect(validateStockSearch({ ma: '' }).ma).toBe('')
    expect(parseMa('')).toEqual([])
  })
})

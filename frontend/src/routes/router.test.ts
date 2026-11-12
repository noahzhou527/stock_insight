import { afterEach, describe, expect, it } from 'vitest'
import { usePrefs } from '@/lib/prefs'
import { parseMa, stockDefaults, validateRankingsSearch, validateStockSearch, validateWatchlistSearch, withoutDefaults } from './search'

afterEach(() => usePrefs.setState({ prefs: {} }))

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

  it('uses saved indicator prefs as defaults, and the URL can still override them', () => {
    usePrefs.setState({ prefs: { stock_defaults: { ma: '10,60', bbi: true, rsi: 9, sub: 'rsi' } } })
    expect(validateStockSearch({})).toMatchObject({ ma: '10,60', bbi: true, boll: false, rsi: 9, sub: 'rsi' })
    expect(validateStockSearch({ bbi: 'false', ma: '5' })).toMatchObject({ bbi: false, ma: '5' })
    // the saved defaults are what gets stripped from URLs
    expect(withoutDefaults({ ...stockDefaults(), range: '3m' }, stockDefaults())).toEqual({ range: '3m' })
  })

  it('ignores corrupt prefs', () => {
    usePrefs.setState({ prefs: { stock_defaults: { rsi: 99, sub: 'kdj' as never } } })
    expect(stockDefaults()).toMatchObject({ rsi: 14, sub: 'volume' })
  })
})

describe('watchlist / rankings search params', () => {
  it('watchlist sort falls back to the saved sort, then to 加入顺序', () => {
    expect(validateWatchlistSearch({})).toEqual({ q: '', sort: 'order', dir: 'desc' })
    usePrefs.setState({ prefs: { watchlist_sort: { sort: 'change_pct', dir: 'asc' } } })
    expect(validateWatchlistSearch({ q: '中际' })).toEqual({ q: '中际', sort: 'change_pct', dir: 'asc' })
    expect(validateWatchlistSearch({ sort: 'bogus', dir: 'up' })).toEqual({ q: '', sort: 'change_pct', dir: 'asc' })
  })

  it('rankings keep metric and leave sort to the metric by default', () => {
    expect(validateRankingsSearch({})).toEqual({ metric: 'change_pct', sort: undefined, dir: undefined })
    expect(validateRankingsSearch({ metric: 'pe_ttm', sort: 'amount', dir: 'asc' })).toEqual({ metric: 'pe_ttm', sort: 'amount', dir: 'asc' })
    expect(validateRankingsSearch({ metric: 'x' }).metric).toBe('change_pct')
  })
})

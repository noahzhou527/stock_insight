import { describe, expect, it } from 'vitest'
import { resolveRange } from './range'

describe('resolveRange', () => {
  it('maps presets against the market date', () => {
    expect(resolveRange('1y', '2026-11-11')).toEqual({ start: '2025-11-11' })
    expect(resolveRange('3m', '2026-11-11')).toEqual({ start: '2026-08-11' })
    expect(resolveRange('ytd', '2026-11-11')).toEqual({ start: '2026-01-01' })
  })

  it('clamps month ends', () => {
    expect(resolveRange('1m', '2026-03-31')).toEqual({ start: '2026-02-28' })
  })

  it('custom keeps explicit dates', () => {
    expect(resolveRange('custom', '2026-11-11', '2026-01-05', '2026-06-30')).toEqual({ start: '2026-01-05', end: '2026-06-30' })
  })
})

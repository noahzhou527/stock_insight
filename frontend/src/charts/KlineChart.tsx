/**
 * Daily K-line with MA overlays and a volume / amount pane (lightweight-charts v5 panes).
 * The time scale is index-based, so weekends, holidays and suspensions leave no gaps.
 */
import {
  CandlestickSeries,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Schemas } from '@/api/client'
import { formatAmount, formatPct, formatPrice, formatVolume, isNum, type Market } from '@/lib/format'
import { useTheme } from '@/theme/theme'
import { alpha, axisVolume, baseOptions, MA_COLORS, readColors } from './chartTheme'

type Bar = Schemas['Bar']
export type SubChart = 'volume' | 'amount'

interface Props {
  bars: Bar[]
  indicators: Record<string, (number | null)[]>
  maKeys: string[]
  sub: SubChart
  market: Market
  currency: string
  height: number
}

interface Legend {
  bar: Bar
  index: number
  change: number | null
}

const NATURAL_SPACING = 8

export function KlineChart({ bars, indicators, maKeys, sub, market, currency, height }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<{ candle?: ISeriesApi<'Candlestick'>; sub?: ISeriesApi<'Histogram'>; ma: ISeriesApi<'Line'>[] }>({ ma: [] })
  const theme = useTheme((s) => s.theme)
  const [legend, setLegend] = useState<Legend | null>(null)
  const indexByTime = useMemo(() => new Map(bars.map((b, i) => [b.date, i])), [bars])
  // Latest data for the crosshair handler (registered once per chart instance).
  const barsRef = useRef(bars)
  const indexByTimeRef = useRef(indexByTime)
  useLayoutEffect(() => {
    barsRef.current = bars
    indexByTimeRef.current = indexByTime
  }, [bars, indexByTime])

  // (Re)create the chart when theme / market / layout inputs change; data updates reuse it.
  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const colors = readColors(element)
    const chart = createChart(element, baseOptions(colors))
    chartRef.current = chart
    const pricePrecision = currency === 'KRW' ? 0 : 2
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.up,
      wickDownColor: colors.down,
      priceFormat: { type: 'price', precision: pricePrecision, minMove: pricePrecision ? 0.01 : 1 },
      priceLineVisible: false,
    })
    const ma = maKeys.map((_, i) =>
      chart.addSeries(LineSeries, {
        color: MA_COLORS[i % MA_COLORS.length],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      }),
    )
    const subSeries = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: 'custom', formatter: (v: number) => axisVolume(v, market), minMove: 1 },
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    )
    chart.panes()[1]?.setStretchFactor(0.28)
    seriesRef.current = { candle, sub: subSeries, ma }

    const onMove = (param: MouseEventParams<Time>) => {
      if (!param.time) {
        setLegend(null)
        return
      }
      const index = indexByTimeRef.current.get(String(param.time))
      if (index === undefined) return
      const bar = barsRef.current[index]
      const prev = barsRef.current[index - 1]
      setLegend({ bar, index, change: prev && isNum(bar.close) && isNum(prev.close) ? (bar.close / prev.close - 1) * 100 : null })
    }
    chart.subscribeCrosshairMove(onMove)
    return () => {
      chart.unsubscribeCrosshairMove(onMove)
      chart.remove()
      chartRef.current = null
    }
  }, [theme, market, currency, maKeys.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const chart = chartRef.current
    const { candle, sub: subSeries, ma } = seriesRef.current
    const element = containerRef.current
    if (!chart || !candle || !subSeries || !element) return
    const colors = readColors(element)
    const valid = bars.filter((b) => isNum(b.open) && isNum(b.close))
    candle.setData(
      valid.map((b) => ({
        time: b.date as Time,
        open: b.open!,
        high: b.high!,
        low: b.low!,
        close: b.close!,
        // 盘中合成的当日 K 线用空心描边区分
        ...(b.provisional ? { color: 'transparent', borderColor: b.close! >= b.open! ? colors.up : colors.down } : {}),
      })),
    )
    subSeries.setData(
      valid.map((b) => ({
        time: b.date as Time,
        value: (sub === 'amount' ? b.amount : b.volume) ?? 0,
        color: alpha(b.close! >= b.open! ? colors.up : colors.down, 0.7),
      })),
    )
    maKeys.forEach((key, i) => {
      const values = indicators[key] ?? []
      ma[i]?.setData(bars.map((b, j) => (isNum(values[j]) ? { time: b.date as Time, value: values[j]! } : { time: b.date as Time })))
    })

    // New listings: keep natural candle width instead of stretching a few bars across the chart.
    const capacity = Math.floor(element.clientWidth / NATURAL_SPACING)
    if (valid.length < capacity * 0.6) {
      chart.timeScale().setVisibleLogicalRange({ from: -2, to: Math.max(capacity * 0.6, valid.length + 4) })
    } else {
      chart.timeScale().fitContent()
    }
  }, [bars, indicators, sub, maKeys, theme, market, currency])

  const last = bars.length ? { bar: bars[bars.length - 1], index: bars.length - 1 } : null
  const shown = legend ?? (last ? { ...last, change: null } : null)
  return (
    <div className="relative" style={{ height }}>
      <div ref={containerRef} className="absolute inset-0" />
      {shown && (
        <div className="pointer-events-none absolute top-1.5 left-2 z-10 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px]">
          <span className="num text-muted">{shown.bar.date}</span>
          {(['open', 'high', 'low', 'close'] as const).map((k) => (
            <span key={k} className="num">
              <span className="text-subtle">{{ open: '开', high: '高', low: '低', close: '收' }[k]} </span>
              <span className="text-fg">{formatPrice(shown.bar[k], currency)}</span>
            </span>
          ))}
          {shown.change !== null && <span className={shown.change >= 0 ? 'num text-up' : 'num text-down'}>{formatPct(shown.change)}</span>}
          {maKeys.map((key, i) => (
            <span key={key} className="num" style={{ color: MA_COLORS[i % MA_COLORS.length] }}>
              {key.toUpperCase()} {formatPrice(indicators[key]?.[shown.index], currency)}
            </span>
          ))}
          <span className="num text-subtle">
            {sub === 'amount' ? `额 ${formatAmount(shown.bar.amount, market, currency)}` : `量 ${formatVolume(shown.bar.volume, market)}`}
          </span>
          {shown.bar.provisional && <span className="text-accent">盘中合成</span>}
        </div>
      )}
    </div>
  )
}

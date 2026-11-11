/**
 * Intraday chart: price + average price, previous-close line, price axis (right) and change-% axis (left),
 * volume pane. Validates the P3 questions for lightweight-charts:
 * - dual axis: a transparent series of % change on the left scale. Both scales get the same symmetric
 *   range around 昨收 (price ±d ↔ ±d/昨收 %), so they stay aligned and the % ticks land on round values.
 * - 午休: the time scale is index-based; the full session is laid out with whitespace points, so 11:30→13:00
 *   is adjacent and the not-yet-traded part of the day is reserved on the axis.
 */
import {
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type AutoscaleInfo,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Schemas } from '@/api/client'
import { formatPct, formatPrice, formatVolume, isNum, type Market } from '@/lib/format'
import { useTheme } from '@/theme/theme'
import { alpha, axisVolume, baseOptions, readColors } from './chartTheme'

type Point = Schemas['IntradayPoint']

interface Props {
  points: Point[]
  preClose: number
  tradeDate: string
  sessions: string[][] // [["09:30","11:30"],["13:00","15:00"]] (market-local)
  market: Market
  currency: string
  height: number
}

/** Market-local wall time encoded as a UTC timestamp so the axis shows local HH:MM. */
function localTs(value: string): UTCTimestamp {
  const [d, t = '00:00:00'] = value.split('T')
  const [y, mo, da] = d.split('-').map(Number)
  const [h, mi, s] = t.split(':').map((x) => Number.parseInt(x, 10))
  return (Date.UTC(y, mo - 1, da, h, mi, s || 0) / 1000) as UTCTimestamp
}

function sessionGrid(tradeDate: string, sessions: string[][], stepMinutes: number): UTCTimestamp[] {
  const out: UTCTimestamp[] = []
  for (const [start, end] of sessions) {
    const from = localTs(`${tradeDate}T${start}:00`)
    const to = localTs(`${tradeDate}T${end}:00`)
    for (let t = from; t <= to; t = (t + stepMinutes * 60) as UTCTimestamp) out.push(t)
  }
  return out
}

const hhmm = (t: number) => {
  const d = new Date(t * 1000)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

export function IntradayChart({ points, preClose, tradeDate, sessions, market, currency, height }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<{ price?: ISeriesApi<'Line'>; avg?: ISeriesApi<'Line'>; pct?: ISeriesApi<'Line'>; vol?: ISeriesApi<'Histogram'> }>({})
  const theme = useTheme((s) => s.theme)
  const [hover, setHover] = useState<Point | null>(null)
  const byTime = useMemo(() => new Map(points.map((p) => [localTs(p.time), p])), [points])
  const byTimeRef = useRef(byTime)
  const rangeRef = useRef<AutoscaleInfo | null>(null)
  const pctRangeRef = useRef<AutoscaleInfo | null>(null)
  useLayoutEffect(() => {
    byTimeRef.current = byTime
  }, [byTime])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const colors = readColors(element)
    const options = baseOptions(colors)
    const chart = createChart(element, {
      ...options,
      leftPriceScale: { ...options.leftPriceScale, visible: true, scaleMargins: { top: 0.1, bottom: 0.06 } },
      rightPriceScale: { ...options.rightPriceScale, scaleMargins: { top: 0.1, bottom: 0.06 } },
      timeScale: { ...options.timeScale, rightOffset: 0, tickMarkFormatter: (t: Time) => hhmm(Number(t)), fixLeftEdge: true, fixRightEdge: true },
      localization: { ...options.localization, timeFormatter: (t: Time) => hhmm(Number(t)) },
      handleScroll: false,
      handleScale: false,
    })
    chartRef.current = chart
    const autoscale = () => rangeRef.current
    const precision = currency === 'KRW' ? 0 : 2
    const price = chart.addSeries(LineSeries, {
      color: colors.fg,
      lineWidth: 1,
      priceFormat: { type: 'price', precision, minMove: precision ? 0.01 : 1 },
      autoscaleInfoProvider: autoscale,
      priceLineVisible: false,
    })
    const avg = chart.addSeries(LineSeries, {
      color: colors.warn,
      lineWidth: 1,
      autoscaleInfoProvider: autoscale,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    const pct = chart.addSeries(LineSeries, {
      color: 'transparent',
      priceScaleId: 'left',
      autoscaleInfoProvider: () => pctRangeRef.current,
      priceFormat: { type: 'custom', minMove: 0.01, formatter: (v: number) => formatPct(v) },
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: false,
    })
    price.createPriceLine({ price: preClose, color: colors.subtle, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '昨收' })
    const vol = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: 'custom', formatter: (v: number) => axisVolume(v, market), minMove: 1 }, priceLineVisible: false, lastValueVisible: false },
      1,
    )
    chart.panes()[1]?.setStretchFactor(0.3)
    seriesRef.current = { price, avg, pct, vol }

    const onMove = (param: MouseEventParams<Time>) => {
      setHover(param.time ? (byTimeRef.current.get(Number(param.time) as UTCTimestamp) ?? null) : null)
    }
    chart.subscribeCrosshairMove(onMove)
    return () => {
      chart.unsubscribeCrosshairMove(onMove)
      chart.remove()
      chartRef.current = null
    }
  }, [theme, market, currency, preClose]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const element = containerRef.current
    const { price, avg, pct, vol } = seriesRef.current
    if (!element || !price || !avg || !pct || !vol || !chartRef.current) return
    const colors = readColors(element)
    const valid = points.filter((p) => isNum(p.price))
    // Symmetric range around 昨收 (A 股惯例), shared by the price and % axes.
    const deviation = Math.max(preClose * 0.002, ...valid.flatMap((p) => [Math.abs(p.price! - preClose), Math.abs((p.avg_price ?? preClose) - preClose)]))
    const d = deviation * 1.08
    rangeRef.current = { priceRange: { minValue: preClose - d, maxValue: preClose + d } }
    pctRangeRef.current = { priceRange: { minValue: (-d / preClose) * 100, maxValue: (d / preClose) * 100 } }

    const step = market === 'CN' ? 1 : 5
    const dataTimes = new Set(valid.map((p) => localTs(p.time)))
    const grid = sessionGrid(tradeDate, sessions, step).filter((t) => !dataTimes.has(t))
    const all = [...valid.map((p) => ({ t: localTs(p.time), p })), ...grid.map((t) => ({ t, p: null as Point | null }))].sort((a, b) => a.t - b.t)

    price.setData(all.map(({ t, p }) => (p ? { time: t, value: p.price! } : { time: t })))
    pct.setData(all.map(({ t, p }) => (p ? { time: t, value: (p.price! / preClose - 1) * 100 } : { time: t })))
    avg.setData(all.map(({ t, p }) => (p && isNum(p.avg_price) ? { time: t, value: p.avg_price } : { time: t })))
    let prev = preClose
    vol.setData(
      all.map(({ t, p }) => {
        if (!p) return { time: t }
        const color = p.price! >= prev ? colors.up : colors.down
        prev = p.price!
        return { time: t, value: p.volume ?? 0, color: alpha(color, 0.75) }
      }),
    )
    chartRef.current.timeScale().fitContent()
  }, [points, preClose, tradeDate, sessions, market, theme, currency])

  const shown = hover ?? points[points.length - 1]
  return (
    <div className="relative" style={{ height }}>
      <div ref={containerRef} className="absolute inset-0" />
      {shown && (
        <div className="pointer-events-none absolute top-1.5 left-14 z-10 flex flex-wrap items-center gap-x-3 text-[11px]">
          <span className="num text-muted">{shown.time.slice(11, 16)}</span>
          <span className="num">
            <span className="text-subtle">价 </span>
            <span className="text-fg">{formatPrice(shown.price, currency)}</span>
          </span>
          <span className={isNum(shown.price) && shown.price >= preClose ? 'num text-up' : 'num text-down'}>
            {isNum(shown.price) ? formatPct((shown.price / preClose - 1) * 100) : '—'}
          </span>
          <span className="num" style={{ color: 'var(--warn)' }}>
            均 {formatPrice(shown.avg_price, currency)}
          </span>
          <span className="num text-subtle">量 {formatVolume(shown.volume, market)}</span>
        </div>
      )}
    </div>
  )
}

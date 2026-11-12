/**
 * Daily K-line with MA / BBI / BOLL overlays and one sub-pane: volume, amount, RSI or MACD
 * (lightweight-charts v5 panes). The time scale is index-based, so weekends, holidays and
 * suspensions leave no gaps.
 */
import {
  CandlestickSeries,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Schemas } from '@/api/client'
import { formatAmount, formatPct, formatPrice, formatRatio, formatVolume, isNum, type Market } from '@/lib/format'
import { useTheme } from '@/theme/theme'
import { alpha, axisVolume, baseOptions, BBI_COLOR, MA_COLORS, readColors, SIGNAL_COLOR } from './chartTheme'

type Bar = Schemas['Bar']
export type SubChart = 'volume' | 'amount' | 'rsi' | 'macd'

interface Props {
  bars: Bar[]
  indicators: Record<string, (number | null)[]>
  maKeys: string[]
  bbi: boolean
  boll: boolean
  rsiPeriod: number
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

interface SeriesSet {
  candle?: ISeriesApi<'Candlestick'>
  ma: ISeriesApi<'Line'>[]
  bbi?: ISeriesApi<'Line'>
  boll: ISeriesApi<'Line'>[]
  hist?: ISeriesApi<'Histogram'>
  subLines: ISeriesApi<'Line'>[]
}

const NATURAL_SPACING = 8
// Empty bar slots kept at each edge so the first and last candles (and their axis labels) are not cut off.
const LEFT_PAD = 3
const RIGHT_PAD = 4
const BOLL_KEYS = ['boll_upper', 'boll_middle', 'boll_lower'] as const
const BOLL_LABEL = { boll_upper: '上', boll_middle: '中', boll_lower: '下' } as const

export function KlineChart({ bars, indicators, maKeys, bbi, boll, rsiPeriod, sub, market, currency, height }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const fitKeyRef = useRef('')
  const fitRangeRef = useRef<{ from: number; to: number } | null>(null)
  const seriesRef = useRef<SeriesSet>({ ma: [], boll: [], subLines: [] })
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

  const rsiKey = `rsi${rsiPeriod}`
  const subKind = sub === 'rsi' || sub === 'macd' ? sub : 'bars'

  // (Re)create the chart when theme / market / layout inputs change; data updates reuse it.
  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const colors = readColors(element)
    const chart = createChart(element, {
      ...baseOptions(colors),
      // extra headroom so the legend row never sits on the highest candles
      rightPriceScale: { ...baseOptions(colors).rightPriceScale, scaleMargins: { top: 0.12, bottom: 0.05 } },
      // Fixed view: the chart always shows the whole selected range (zooming in cut candles off at the edges).
      // Use the range buttons / custom dates to look at a shorter period. The mouse wheel scrolls the page.
      handleScroll: false,
      handleScale: false,
    })
    chartRef.current = chart
    fitKeyRef.current = '' // a new chart instance always starts fitted
    const pricePrecision = currency === 'KRW' ? 0 : 2
    const overlay = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false } as const
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
    const ma = maKeys.map((_, i) => chart.addSeries(LineSeries, { ...overlay, color: MA_COLORS[i % MA_COLORS.length] }))
    const bbiSeries = bbi ? chart.addSeries(LineSeries, { ...overlay, color: BBI_COLOR, lineStyle: LineStyle.Dashed }) : undefined
    const bollSeries = boll
      ? BOLL_KEYS.map((key) =>
          chart.addSeries(LineSeries, {
            ...overlay,
            color: alpha(colors.accent, key === 'boll_middle' ? 0.55 : 0.9),
            lineStyle: key === 'boll_middle' ? LineStyle.Dotted : LineStyle.Solid,
          }),
        )
      : []

    let hist: ISeriesApi<'Histogram'> | undefined
    const subLines: ISeriesApi<'Line'>[] = []
    if (subKind === 'bars') {
      hist = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: 'custom', formatter: (v: number) => axisVolume(v, market), minMove: 1 }, priceLineVisible: false, lastValueVisible: false },
        1,
      )
    } else if (subKind === 'rsi') {
      const line = chart.addSeries(
        LineSeries,
        {
          ...overlay,
          color: colors.accent,
          lastValueVisible: true,
          priceFormat: { type: 'price', precision: 1, minMove: 0.1 },
          autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
        },
        1,
      )
      for (const [level, title] of [[70, '超买'], [30, '超卖']] as const) {
        line.createPriceLine({ price: level, color: colors.subtle, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title })
      }
      subLines.push(line)
    } else {
      const format = { type: 'price', precision: pricePrecision ? 2 : 0, minMove: pricePrecision ? 0.01 : 1 } as const
      hist = chart.addSeries(HistogramSeries, { priceFormat: format, priceLineVisible: false, lastValueVisible: false }, 1)
      subLines.push(
        chart.addSeries(LineSeries, { ...overlay, color: colors.accent, priceFormat: format }, 1),
        chart.addSeries(LineSeries, { ...overlay, color: SIGNAL_COLOR, priceFormat: format }, 1),
      )
    }
    chart.panes()[1]?.setStretchFactor(0.28)
    seriesRef.current = { candle, ma, bbi: bbiSeries, boll: bollSeries, hist, subLines }

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
    // The library keeps bar width on resize; keep the whole range visible instead.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
      if (fitRangeRef.current) requestAnimationFrame(() => chartRef.current?.timeScale().setVisibleLogicalRange(fitRangeRef.current!))
    })
    observer?.observe(element)
    return () => {
      observer?.disconnect()
      chart.unsubscribeCrosshairMove(onMove)
      chart.remove()
      chartRef.current = null
    }
  }, [theme, market, currency, maKeys.join(','), bbi, boll, subKind]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const chart = chartRef.current
    const { candle, ma, bbi: bbiSeries, boll: bollSeries, hist, subLines } = seriesRef.current
    const element = containerRef.current
    if (!chart || !candle || !element) return
    const colors = readColors(element)
    const valid = bars.filter((b) => isNum(b.open) && isNum(b.close))
    const line = (key: string) => {
      const values = indicators[key] ?? []
      return bars.map((b, j) => (isNum(values[j]) ? { time: b.date as Time, value: values[j]! } : { time: b.date as Time }))
    }
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
    maKeys.forEach((key, i) => ma[i]?.setData(line(key)))
    bbiSeries?.setData(line('bbi'))
    BOLL_KEYS.forEach((key, i) => bollSeries[i]?.setData(line(key)))

    if (sub === 'volume' || sub === 'amount') {
      hist?.setData(
        valid.map((b) => ({
          time: b.date as Time,
          value: (sub === 'amount' ? b.amount : b.volume) ?? 0,
          color: alpha(b.close! >= b.open! ? colors.up : colors.down, 0.7),
        })),
      )
    } else if (sub === 'rsi') {
      subLines[0]?.setData(line(rsiKey))
    } else {
      const values = indicators.macd_hist ?? []
      hist?.setData(
        bars.map((b, j) =>
          isNum(values[j]) ? { time: b.date as Time, value: values[j]!, color: alpha(values[j]! >= 0 ? colors.up : colors.down, 0.75) } : { time: b.date as Time },
        ),
      )
      subLines[0]?.setData(line('macd'))
      subLines[1]?.setData(line('macd_signal'))
    }

    // Fit only when the range itself changes (a 30-second refresh of the same range needs no refit).
    const fitKey = `${valid[0]?.date}|${valid.length}`
    if (fitKeyRef.current === fitKey) return
    fitKeyRef.current = fitKey
    const capacity = Math.floor(element.clientWidth / NATURAL_SPACING)
    // New listings: keep natural candle width instead of stretching a few bars across the chart.
    const range = valid.length < capacity * 0.6
      ? { from: -LEFT_PAD, to: Math.max(capacity * 0.6, valid.length + RIGHT_PAD) }
      : { from: -LEFT_PAD, to: valid.length - 1 + RIGHT_PAD }
    fitRangeRef.current = range
    chart.timeScale().setVisibleLogicalRange(range)
  }, [bars, indicators, sub, subKind, rsiKey, maKeys, bbi, boll, theme, market, currency])

  const last = bars.length ? { bar: bars[bars.length - 1], index: bars.length - 1 } : null
  const shown = legend ?? (last ? { ...last, change: null } : null)
  const at = (key: string) => (shown ? indicators[key]?.[shown.index] : null)
  const subEmpty =
    (sub === 'rsi' && !(indicators[rsiKey] ?? []).some(isNum)) || (sub === 'macd' && !(indicators.macd ?? []).some(isNum))
  const macdDigits = currency === 'KRW' ? 0 : 2
  const summary = last
    ? `日 K 线图，共 ${bars.length} 个交易日，${bars[0].date} 至 ${last.bar.date}，最新收盘 ${formatPrice(last.bar.close, currency)}`
    : '日 K 线图'
  return (
    <div className="relative" style={{ height }} role="img" aria-label={summary}>
      <div ref={containerRef} className="absolute inset-0" />
      {shown && (
        <div className="pointer-events-none absolute top-1.5 right-16 left-2 z-10 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px]">
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
              {key.toUpperCase()} {formatPrice(at(key), currency)}
            </span>
          ))}
          {bbi && (
            <span className="num" style={{ color: BBI_COLOR }}>
              BBI {formatPrice(at('bbi'), currency)}
            </span>
          )}
          {boll && (
            <span className="num text-accent">
              BOLL {BOLL_KEYS.map((key) => `${BOLL_LABEL[key]} ${formatPrice(at(key), currency)}`).join(' ')}
            </span>
          )}
          {sub === 'amount' && <span className="num text-subtle">额 {formatAmount(shown.bar.amount, market, currency)}</span>}
          {sub === 'volume' && <span className="num text-subtle">量 {formatVolume(shown.bar.volume, market)}</span>}
          {sub === 'rsi' && (
            <span className="num text-accent">
              RSI({rsiPeriod}) {formatRatio(at(rsiKey), 1)}
            </span>
          )}
          {sub === 'macd' && (
            <>
              <span className="num text-accent">MACD {formatRatio(at('macd'), macdDigits)}</span>
              <span className="num" style={{ color: SIGNAL_COLOR }}>
                信号 {formatRatio(at('macd_signal'), macdDigits)}
              </span>
              <span className="num text-subtle">柱 {formatRatio(at('macd_hist'), macdDigits)}</span>
            </>
          )}
          {shown.bar.provisional && <span className="text-accent">盘中合成</span>}
        </div>
      )}
      {subEmpty && (
        <div className="pointer-events-none absolute inset-x-0 bottom-9 z-10 text-center text-[12px] text-subtle">
          历史日 K 不足，暂无法计算 {sub === 'rsi' ? `RSI(${rsiPeriod})` : 'MACD'}
        </div>
      )}
    </div>
  )
}

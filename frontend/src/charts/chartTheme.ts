/** Chart colours resolved from CSS tokens at the chart's DOM position (so data-market up/down applies). */
import { ColorType, CrosshairMode, LineStyle, type DeepPartial, type ChartOptions } from 'lightweight-charts'

export interface ChartColors {
  bg: string
  text: string
  subtle: string
  grid: string
  line: string
  crosshair: string
  accent: string
  warn: string
  up: string
  down: string
  flat: string
  fg: string
}

export const MA_COLORS = ['#f5a524', '#38bdf8', '#c084fc', '#f472b6', '#34d399', '#fb923c', '#a3e635']

export const BBI_COLOR = '#e879f9'
export const SIGNAL_COLOR = '#f5a524'
export const REVENUE_COLOR = '#22d3ee'
export const PROFIT_COLOR = '#8b5cf6'

export function readColors(element: Element): ChartColors {
  const style = getComputedStyle(element)
  const v = (name: string) => style.getPropertyValue(name).trim()
  return {
    bg: v('--bg-panel'),
    text: v('--text-2'),
    subtle: v('--text-3'),
    grid: v('--chart-grid'),
    line: v('--line'),
    crosshair: v('--chart-crosshair'),
    accent: v('--accent'),
    warn: v('--warn'),
    up: v('--up'),
    down: v('--down'),
    flat: v('--flat'),
    fg: v('--text-1'),
  }
}

export function baseOptions(c: ChartColors): DeepPartial<ChartOptions> {
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: c.bg },
      textColor: c.text,
      fontSize: 11,
      fontFamily: getComputedStyle(document.body).fontFamily,
      attributionLogo: false,
      panes: { separatorColor: c.line, separatorHoverColor: c.line, enableResize: true },
    },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: c.crosshair, style: LineStyle.Dashed, labelBackgroundColor: c.crosshair },
      horzLine: { color: c.crosshair, style: LineStyle.Dashed, labelBackgroundColor: c.crosshair },
    },
    rightPriceScale: { borderColor: c.line, scaleMargins: { top: 0.08, bottom: 0.06 } },
    leftPriceScale: { borderColor: c.line },
    timeScale: { borderColor: c.line, rightOffset: 3, barSpacing: 7, minBarSpacing: 1.5 },
    localization: { locale: 'zh-CN' },
  }
}

/** '#e53935' + 0.7 → 'rgba(229, 57, 53, 0.7)' (lightweight-charts does not parse CSS color-mix). */
export function alpha(color: string, a: number): string {
  const hex = color.replace('#', '')
  if (!/^[0-9a-f]{6}$/i.test(hex)) return color
  const n = Number.parseInt(hex, 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

/** Short axis labels: 1.2亿 / 3.4万 (CN/KR) or 1.2M / 3.4K (US). */
export function axisVolume(value: number, market: string): string {
  const abs = Math.abs(value)
  if (market === 'US') {
    if (abs >= 1e9) return `${(value / 1e9).toFixed(1)}B`
    if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`
    if (abs >= 1e3) return `${(value / 1e3).toFixed(0)}K`
    return value.toFixed(0)
  }
  if (abs >= 1e8) return `${(value / 1e8).toFixed(1)}亿`
  if (abs >= 1e4) return `${(value / 1e4).toFixed(0)}万`
  return value.toFixed(0)
}

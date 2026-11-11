/**
 * Small bar charts for 财报 and 同业对比 (§6.4 BarChart). Plain SVG / CSS — a handful of bars with
 * direct value labels does not need the charting library.
 */
import { useLayoutEffect, useRef, useState } from 'react'
import { isNum } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface BarSeries {
  name: string
  color: string
  values: (number | null | undefined)[]
}

function useWidth(ref: React.RefObject<HTMLElement | null>) {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const update = () => setWidth(element.clientWidth)
    update()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return width
}

export function Legend({ series }: { series: { name: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
      {series.map((s) => (
        <span key={s.name} className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-[2px]" style={{ background: s.color }} aria-hidden />
          {s.name}
        </span>
      ))}
    </div>
  )
}

/** Vertical grouped bars: one group per category (报告期), one bar per series. */
export function GroupedBars({
  title,
  categories,
  series,
  format,
  height = 230,
}: {
  title: string
  categories: string[]
  series: BarSeries[]
  format: (value: number) => string
  height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const width = useWidth(ref)
  const values = series.flatMap((s) => s.values).filter(isNum)
  const max = Math.max(0, ...values)
  const min = Math.min(0, ...values)
  const span = max - min || 1
  const top = 18
  const bottom = 22
  const plot = height - top - bottom
  const y = (value: number) => top + ((max - value) / span) * plot
  const groupWidth = categories.length ? width / categories.length : 0
  const barWidth = Math.max(4, Math.min(34, (groupWidth * 0.72) / Math.max(series.length, 1)))
  const summary = `${title}：${categories
    .map((c, i) => `${c} ${series.map((s) => `${s.name} ${isNum(s.values[i]) ? format(s.values[i]!) : '无'}`).join('，')}`)
    .join('；')}`
  return (
    <figure className="m-0 min-w-0">
      <figcaption className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-fg">{title}</span>
        <Legend series={series} />
      </figcaption>
      <div ref={ref} style={{ height }}>
        {width > 0 && (
          <svg width={width} height={height} role="img" aria-label={summary}>
            <line x1={0} x2={width} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" />
            {categories.map((category, i) => {
              const center = groupWidth * (i + 0.5)
              const start = center - (barWidth * series.length) / 2
              return (
                <g key={category}>
                  {series.map((s, j) => {
                    const value = s.values[i]
                    if (!isNum(value)) return null
                    const yTop = Math.min(y(value), y(0))
                    const barHeight = Math.max(1, Math.abs(y(value) - y(0)))
                    const x = start + j * barWidth
                    return (
                      <g key={s.name}>
                        <rect x={x + 1} y={yTop} width={barWidth - 2} height={barHeight} rx={1.5} fill={s.color} opacity={0.9} />
                        <text
                          x={x + barWidth / 2}
                          y={value >= 0 ? yTop - 4 : yTop + barHeight + 11}
                          textAnchor="middle"
                          fontSize={10}
                          fill="var(--text-2)"
                          style={{ fontVariantNumeric: 'tabular-nums' }}
                        >
                          {format(value)}
                        </text>
                      </g>
                    )
                  })}
                  <text x={center} y={height - 6} textAnchor="middle" fontSize={11} fill="var(--text-3)" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {category}
                  </text>
                </g>
              )
            })}
          </svg>
        )}
      </div>
    </figure>
  )
}

export interface RankRow {
  id: string
  label: string
  values: (number | null | undefined)[]
  highlight?: boolean
}

/** Horizontal ranked bars: one row per stock, one thin bar per series, shared scale. */
export function RankBars({
  rows,
  series,
  format,
  onRowClick,
  label,
}: {
  rows: RankRow[]
  series: { name: string; color: string }[]
  format: (value: number) => string
  onRowClick?: (id: string) => void
  label: string
}) {
  const values = rows.flatMap((r) => r.values).filter(isNum)
  const max = Math.max(0, ...values)
  const min = Math.min(0, ...values)
  const span = max - min || 1
  const zero = ((0 - min) / span) * 100
  return (
    <div role="list" aria-label={label} className="flex flex-col">
      {rows.map((row) => (
        <div
          key={row.id}
          role="listitem"
          tabIndex={onRowClick ? 0 : undefined}
          onClick={onRowClick ? () => onRowClick(row.id) : undefined}
          onKeyDown={onRowClick ? (e) => e.key === 'Enter' && onRowClick(row.id) : undefined}
          className={cn('grid grid-cols-[104px_1fr] items-center gap-2 rounded px-1 py-1', onRowClick && 'cursor-pointer hover:bg-raised')}
        >
          <span className={cn('truncate text-[12px]', row.highlight ? 'font-semibold text-accent' : 'text-muted')} title={row.label}>
            {row.label}
          </span>
          <div className="flex min-w-0 flex-col gap-0.5">
            {series.map((s, i) => {
              const value = row.values[i]
              if (!isNum(value)) {
                return (
                  <div key={s.name} className="h-3.5 text-[10px] leading-[14px] text-subtle" style={{ paddingLeft: `${zero}%` }}>
                    无数据
                  </div>
                )
              }
              const size = (Math.abs(value) / span) * 100
              const left = value >= 0 ? zero : zero - size
              const labelInside = left + size > 82
              return (
                <div key={s.name} className="relative h-3.5">
                  <div
                    className="absolute inset-y-[2px] rounded-[2px]"
                    style={{ left: `${left}%`, width: `max(${size}%, 2px)`, background: s.color, opacity: row.highlight ? 1 : 0.72 }}
                  />
                  <span
                    className={cn('num absolute top-0 text-[10px] leading-[14px] whitespace-nowrap', labelInside ? 'text-app' : 'text-muted')}
                    style={labelInside ? { right: `${100 - left - size + 0.8}%` } : { left: `calc(${left + size}% + 4px)` }}
                  >
                    {format(value)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

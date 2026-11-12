/** One "label value" pair in a chart legend: muted label, tabular value, a clear gap between the two. */
import type { ReactNode } from 'react'

export function LegendItem({ label, color, children }: { label: string; color?: string; children: ReactNode }) {
  return (
    <span className="num inline-flex items-baseline gap-1.5 whitespace-nowrap" style={color ? { color } : undefined}>
      <span className={color ? 'opacity-80' : 'text-subtle'}>{label}</span>
      <span>{children}</span>
    </span>
  )
}

/** 分时迷你走势 (自选可选列). Loads the stock's intraday only when the column is shown. */
import { useIntraday } from '@/api/queries'
import { isNum, type Market } from '@/lib/format'

const W = 84
const H = 24

export function IntradaySparkline({ market, symbol }: { market: Market; symbol: string }) {
  const query = useIntraday(market, symbol)
  const data = query.data
  if (!data) return <span className="inline-block h-6 w-[84px] animate-pulse rounded bg-raised align-middle" aria-hidden />
  const prices = data.points.map((p) => p.price).filter(isNum)
  if (prices.length < 2) return <span className="text-[11px] text-subtle">—</span>
  const base = data.pre_close
  const deviation = Math.max(...prices.map((p) => Math.abs(p - base)), base * 0.002)
  const y = (v: number) => H / 2 - ((v - base) / deviation) * (H / 2 - 1)
  const step = W / (prices.length - 1)
  const path = prices.map((p, i) => `${(i * step).toFixed(1)},${y(p).toFixed(1)}`).join(' ')
  const last = prices[prices.length - 1]
  const tone = last > base ? 'var(--up)' : last < base ? 'var(--down)' : 'var(--flat)'
  return (
    <svg width={W} height={H} className="inline-block align-middle" role="img" aria-label={`${data.trade_date} 分时走势，${last >= base ? '高于' : '低于'}昨收`}>
      <line x1={0} x2={W} y1={H / 2} y2={H / 2} stroke="var(--line-strong)" strokeDasharray="2 2" />
      <polyline points={path} fill="none" stroke={tone} strokeWidth={1.2} />
    </svg>
  )
}

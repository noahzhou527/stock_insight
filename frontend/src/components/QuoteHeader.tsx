/** 报价头 + 属性条 (§6.2). The price is the only large text on the page. */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Star } from 'lucide-react'
import { api, ApiError, type Schemas } from '@/api/client'
import {
  currencySymbol,
  DASH,
  formatMoneyShort,
  formatPct,
  formatPrice,
  formatRatio,
  formatSigned,
  formatVolume,
  isNum,
  type Market,
} from '@/lib/format'
import { cn } from '@/lib/utils'
import { DataStatusBadge } from './DataStatusBadge'
import { ChangeText } from './states'
import { Button, Segmented, Skeleton, Tip } from './ui'

const MARKET_LABEL: Record<Market, string> = { CN: 'A股', US: '美股', KR: '韩股' }

export function QuoteHeader({
  market,
  symbol,
  snapshot,
  currency,
  onCurrency,
}: {
  market: Market
  symbol: string
  snapshot: Schemas['SnapshotResponse'] | undefined
  currency: string
  onCurrency: (c: string) => void
}) {
  const m = snapshot?.metrics
  const info = snapshot?.instrument
  const firstDay = snapshot && !isNum(m?.pre_close)
  return (
    <section className="flex flex-wrap items-end gap-x-6 gap-y-2 px-4 pt-3 pb-2" aria-label="报价">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="truncate text-[17px] font-semibold text-fg">{info?.name ?? (snapshot ? symbol : <Skeleton className="h-5 w-24" />)}</h1>
          <span className="num text-[13px] text-muted">{symbol}</span>
          <span className="rounded border border-line px-1 text-[10px] leading-4 text-subtle">{MARKET_LABEL[market]}</span>
          {info?.groups.slice(0, 2).map((g) => (
            <span key={g} className="rounded bg-raised px-1.5 text-[11px] leading-[18px] text-muted">
              {g}
            </span>
          ))}
          {market === 'CN' && info && <WatchButton market={market} symbol={symbol} inWatchlist={info.in_watchlist} />}
        </div>
        <div className="mt-1 flex items-baseline gap-3">
          {m ? (
            <>
              <ChangeText value={m.change} className="text-[30px] leading-none font-semibold tracking-tight">
                <span className="mr-0.5 text-[18px] font-normal">{currencySymbol(currency)}</span>
                {formatPrice(m.price, currency)}
              </ChangeText>
              {firstDay ? (
                <span className="text-[13px] text-muted">首日上市，暂无前收盘价</span>
              ) : (
                <ChangeText value={m.change} className="text-[15px] font-medium">
                  {formatSigned(m.change, currency === 'KRW' ? 0 : 2)}　{formatPct(m.change_pct)}
                </ChangeText>
              )}
              <span className="text-[11px] text-subtle">{m.price_from_intraday ? '分时最新价' : '最近收盘价'}</span>
            </>
          ) : (
            <Skeleton className="h-8 w-56" />
          )}
        </div>
      </div>
      <div className="flex flex-1 items-center justify-end gap-2 pb-0.5">
        <DataStatusBadge meta={snapshot?.meta} />
        {market === 'KR' && (
          <Segmented
            label="显示币种"
            value={currency}
            onChange={onCurrency}
            options={[
              { value: 'KRW', label: '₩ 韩元' },
              { value: 'USD', label: '$ 美元' },
            ]}
          />
        )}
      </div>
      {snapshot?.fx && (
        <div className="w-full text-[11px] text-subtle">
          参考汇率 1 {snapshot.fx.from} = {snapshot.fx.rate.toPrecision(4)} {snapshot.fx.to}（{snapshot.fx.source}），全区间按同一汇率换算
        </div>
      )}
    </section>
  )
}

function WatchButton({ market, symbol, inWatchlist }: { market: Market; symbol: string; inWatchlist: boolean }) {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: () =>
      inWatchlist
        ? api.del(`/api/watchlist/items/${market}/${encodeURIComponent(symbol)}`)
        : api.post('/api/watchlist/items', { code: symbol }),
    onSettled: () => {
      client.invalidateQueries({ queryKey: ['watchlist'] })
      client.invalidateQueries({ queryKey: ['snapshot', market, symbol] })
    },
  })
  const error = mutation.error instanceof ApiError ? mutation.error.message : null
  return (
    <Tip content={error ?? (inWatchlist ? '移出自选' : '加入自选')}>
      <Button
        variant={inWatchlist ? 'accent' : 'ghost'}
        size="sm"
        className="h-6 px-1.5"
        disabled={mutation.isPending}
        aria-pressed={inWatchlist}
        onClick={() => mutation.mutate()}
      >
        <Star className={cn('h-3.5 w-3.5', inWatchlist && 'fill-current')} />
        <span className="text-[12px]">{inWatchlist ? '已自选' : '自选'}</span>
      </Button>
    </Tip>
  )
}

function Cell({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  const content = (
    <div className="flex shrink-0 flex-col gap-0.5 px-3 first:pl-4">
      <span className="text-[11px] whitespace-nowrap text-subtle">{label}</span>
      <span className="num text-[13px] whitespace-nowrap text-fg">{children}</span>
    </div>
  )
  return hint ? <Tip content={hint}>{content}</Tip> : content
}

export function AttributeBar({ snapshot, market, currency }: { snapshot: Schemas['SnapshotResponse'] | undefined; market: Market; currency: string }) {
  if (!snapshot) {
    return (
      <div className="flex gap-6 border-y border-line px-4 py-2">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-8 w-20" />
        ))}
      </div>
    )
  }
  const m = snapshot.metrics
  const v = snapshot.valuation
  const lacking = '数据不足'
  const pe = (value: number | null | undefined) => (isNum(value) ? value.toFixed(1) : market === 'CN' && v ? '亏损/不适用' : DASH)
  const price = (value: number | null | undefined) => formatPrice(value, currency)
  return (
    <div className="flex overflow-x-auto border-y border-line py-1.5 [scrollbar-width:none]" role="list" aria-label="关键属性">
      <Cell label="区间最高 / 最低">
        {price(m.range_high)} <span className="text-subtle">/</span> {price(m.range_low)}
      </Cell>
      <Cell label="52周最高 / 最低">
        {price(m.high_52w)} <span className="text-subtle">/</span> {price(m.low_52w)}
      </Cell>
      <Cell label="区间均量">{formatVolume(m.avg_volume, market)}</Cell>
      <Cell label="区间最大成交额" hint={m.max_amount_date ? `出现于 ${m.max_amount_date}` : undefined}>
        {formatMoneyShort(m.max_amount, currency)}
        {m.max_amount_date && <span className="ml-1 text-[11px] text-subtle">{m.max_amount_date.slice(5)}</span>}
      </Cell>
      <Cell label="年化波动率">{isNum(m.volatility) ? formatRatio(m.volatility, 1, '%') : lacking}</Cell>
      <Cell label="总市值">{formatMoneyShort(v?.market_cap, currency)}</Cell>
      {market === 'CN' && (
        <>
          <Cell label="PE TTM / 静 / 动" hint={v?.source}>
            {pe(v?.pe_ttm)} <span className="text-subtle">/</span> {pe(v?.pe_static)} <span className="text-subtle">/</span> {pe(v?.pe_dynamic)}
          </Cell>
          <Cell label="TTM 净利润">{formatMoneyShort(v?.ttm_net_profit, currency)}</Cell>
        </>
      )}
      {snapshot.new_listing.is_new_listing && (
        <Cell label="上市以来">
          <span className="text-accent">{snapshot.new_listing.daily_bars} 根日 K</span>
        </Cell>
      )}
    </div>
  )
}

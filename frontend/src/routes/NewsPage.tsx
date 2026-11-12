/** /news — Yahoo + 同花顺 + 抖音热点, last 72 hours, de-duplicated and time-sorted by the backend (§8 新闻). */
import { useNavigate } from '@tanstack/react-router'
import { ExternalLink } from 'lucide-react'
import type { Schemas } from '@/api/client'
import { useNews } from '@/api/queries'
import { PageHeader, RefreshButton } from '@/components/common'
import { DataStatusBadge } from '@/components/DataStatusBadge'
import { EmptyState, ErrorState } from '@/components/states'
import { Segmented, Skeleton, Tip } from '@/components/ui'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { newsRoute } from './router'
import type { NewsSearch } from './search'

type Item = Schemas['NewsItemOut']

const SOURCE_TONE: Record<string, string> = {
  Yahoo: 'text-[#a78bfa] border-[#a78bfa]/35',
  同花顺: 'text-accent border-accent/35',
  抖音: 'text-[#f472b6] border-[#f472b6]/35',
}

function NewsRow({ item }: { item: Item }) {
  const observedOnly = !item.published_at
  return (
    <li className="group flex items-start gap-3 border-b border-line px-3 py-2.5 last:border-b-0 hover:bg-raised">
      <Tip content={observedOnly ? '该来源没有发布时间，显示首次看到的时间' : '发布时间'}>
        <span tabIndex={0} className={cn('num w-[84px] shrink-0 pt-px text-[12px]', observedOnly ? 'text-subtle italic' : 'text-muted')}>
          {formatRelativeTime(item.time)}
        </span>
      </Tip>
      <span className={cn('shrink-0 rounded border px-1.5 text-[11px] leading-[18px]', SOURCE_TONE[item.source] ?? 'border-line text-muted')}>{item.source}</span>
      <a href={item.url} target="_blank" rel="noopener noreferrer" className="min-w-0 flex-1 text-[13.5px] leading-snug text-fg hover:text-accent">
        {item.title}
        <ExternalLink className="ml-1 inline h-3 w-3 align-[-1px] text-subtle opacity-0 group-hover:opacity-100" aria-label="（在新窗口打开）" />
      </a>
    </li>
  )
}

export function NewsPage() {
  const search = newsRoute.useSearch() as NewsSearch
  const navigate = useNavigate({ from: newsRoute.fullPath })
  const query = useNews()
  const data = query.data
  const sources = data?.sources.map((s) => s.source) ?? []
  const filter = search.source && sources.includes(search.source) ? search.source : 'all'
  const items = (data?.items ?? []).filter((i) => filter === 'all' || i.source === filter)

  return (
    <div className="min-w-0 pb-10">
      <PageHeader title="财经新闻" sub="最近 72 小时 · Yahoo、同花顺、抖音热点 · 已去重，按时间排序">
        {data?.meta.freshness === 'cached' ? (
          <DataStatusBadge meta={data.meta} />
        ) : (
          data?.meta.fetched_at && <span className="num text-[12px] text-subtle">抓取于 {formatRelativeTime(data.meta.fetched_at + 'Z')}</span>
        )}
        <RefreshButton body={{ target: 'news' }} invalidate={[['news']]} tip="重新抓取新闻" />
      </PageHeader>
      <div className="mx-auto max-w-[960px] space-y-3 px-4">
        {data && (
          <Segmented
            label="来源"
            value={filter}
            onChange={(v) => navigate({ search: { source: v === 'all' ? undefined : v }, replace: true })}
            options={[{ value: 'all', label: `全部 ${data.items.length}` }, ...sources.map((s) => ({ value: s, label: `${s} ${data.items.filter((i) => i.source === s).length}` }))]}
          />
        )}
        {query.isError && !data ? (
          <ErrorState error={query.error} title="新闻加载失败" onRetry={() => query.refetch()} className="rounded-md border border-line bg-panel" />
        ) : !data ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-9" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState title="最近 72 小时暂未读取到可显示的财经新闻" className="rounded-md border border-line bg-panel py-16" />
        ) : (
          <ul className="overflow-hidden rounded-md border border-line bg-panel" aria-label="新闻列表">
            {items.map((item) => (
              <NewsRow key={item.url + item.title} item={item} />
            ))}
          </ul>
        )}
        {data && (
          <footer className="rounded-md border border-line bg-panel px-3 py-2" aria-label="新闻来源状态">
            <div className="mb-1 text-[12px] font-medium text-muted">来源状态</div>
            <ul className="flex flex-wrap gap-x-6 gap-y-1 text-[12px]">
              {data.sources.map((s) => (
                <li key={s.source} className="flex items-center gap-1.5">
                  <span className="text-fg">{s.source}</span>
                  <span className="text-subtle">{s.status}</span>
                </li>
              ))}
            </ul>
            {data.meta.note && <p className="mt-1 text-[11px] text-subtle">{data.meta.note}</p>}
          </footer>
        )}
      </div>
    </div>
  )
}

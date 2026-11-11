/** ⓘ popover with an indicator's definition (§6.1: 指标说明不再是页面). Click or keyboard to open. */
import * as Popover from '@radix-ui/react-popover'
import { Info } from 'lucide-react'
import { INDICATOR_HELP, type IndicatorHelp, type IndicatorKey } from '@/lib/indicatorHelp'
import { cn } from '@/lib/utils'

export function InfoTip({ topic, className }: { topic: IndicatorKey; className?: string }) {
  const help: IndicatorHelp = INDICATOR_HELP[topic]
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`${help.title} 说明`}
          className={cn('inline-flex h-4 w-4 cursor-pointer items-center justify-center rounded-full text-subtle hover:text-fg', className)}
        >
          <Info className="h-3 w-3" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="z-50 w-[340px] max-w-[calc(100vw-24px)] rounded-md border border-line-strong bg-panel p-3 text-[12px] leading-relaxed text-fg shadow-pop"
        >
          <div className="mb-1.5 text-[13px] font-semibold">{help.title}</div>
          {help.formula && <div className="num mb-2 rounded bg-raised px-2 py-1 text-muted">{help.formula}</div>}
          <ul className="list-disc space-y-1 pl-4 text-muted">
            {help.points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <div className="mt-2 text-[11px] text-subtle">用于理解数据口径，不构成投资建议。</div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

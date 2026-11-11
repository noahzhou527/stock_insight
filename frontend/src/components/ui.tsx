/** Small shadcn-style primitives (source lives in the repo and is fully ours to change). */
import * as ToggleGroup from '@radix-ui/react-toggle-group'
import * as Tooltip from '@radix-ui/react-tooltip'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium transition-colors disabled:pointer-events-none disabled:opacity-40 cursor-pointer select-none',
  {
    variants: {
      variant: {
        default: 'bg-raised text-fg hover:bg-line-strong/60 border border-line',
        ghost: 'text-muted hover:text-fg hover:bg-raised',
        accent: 'bg-accent-weak text-accent hover:bg-accent/20 border border-accent/30',
        outline: 'border border-line text-muted hover:text-fg hover:border-line-strong',
      },
      size: { sm: 'h-7 px-2.5', md: 'h-8 px-3', icon: 'h-8 w-8', iconSm: 'h-7 w-7' },
    },
    defaultVariants: { variant: 'default', size: 'md' },
  },
)

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
)
Button.displayName = 'Button'

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
  size = 'sm',
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: ReactNode; title?: string; disabled?: boolean }[]
  label: string
  className?: string
  size?: 'sm' | 'xs'
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as T)}
      aria-label={label}
      className={cn('inline-flex rounded-md border border-line bg-panel p-0.5', className)}
    >
      {options.map((option) => (
        <ToggleGroup.Item
          key={option.value}
          value={option.value}
          title={option.title}
          disabled={option.disabled}
          className={cn(
            'rounded-[5px] font-medium text-muted transition-colors hover:text-fg cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed',
            'data-[state=on]:bg-raised data-[state=on]:text-fg data-[state=on]:shadow-[inset_0_0_0_1px_var(--line-strong)]',
            size === 'sm' ? 'h-6 px-2.5 text-[12px]' : 'h-5 px-2 text-[11px]',
          )}
        >
          {option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  )
}

export function Tip({ content, children, side = 'top' }: { content: ReactNode; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-[320px] rounded-md border border-line-strong bg-panel px-2.5 py-1.5 text-[12px] leading-relaxed text-fg shadow-pop"
        >
          {content}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-raised', className)} />
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line bg-raised px-1.5 py-px font-mono text-[10px] text-subtle">{children}</kbd>
  )
}

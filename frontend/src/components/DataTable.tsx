/**
 * The one table component (§6.4): header sorting, row click, virtual scrolling, column visibility,
 * numeric right-alignment and a sticky first column on narrow screens. Used by 自选 / 排行 / 数据明细.
 */
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type VisibilityState,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { useRef, useState } from 'react'
import { cn } from '@/lib/utils'

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    numeric?: boolean
    width?: number
  }
}

const VIRTUALIZE_ABOVE = 150

export interface DataTableProps<T> {
  data: T[]
  columns: ColumnDef<T, any>[] // eslint-disable-line @typescript-eslint/no-explicit-any
  onRowClick?: (row: T) => void
  getRowId?: (row: T) => string
  sorting?: SortingState
  onSortingChange?: (sorting: SortingState) => void
  columnVisibility?: VisibilityState
  height?: number | string
  rowHeight?: number
  emptyText?: string
  label: string
}

export function DataTable<T>({
  data,
  columns,
  onRowClick,
  getRowId,
  sorting: controlledSorting,
  onSortingChange,
  columnVisibility,
  height = 480,
  rowHeight = 34,
  emptyText = '暂无数据',
  label,
}: DataTableProps<T>) {
  const [localSorting, setLocalSorting] = useState<SortingState>([])
  const sorting = controlledSorting ?? localSorting
  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: (updater) => {
      const next = typeof updater === 'function' ? updater(sorting) : updater
      if (onSortingChange) onSortingChange(next)
      else setLocalSorting(next)
    },
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    sortDescFirst: true,
  })
  const rows = table.getRowModel().rows
  const parentRef = useRef<HTMLDivElement>(null)
  // Virtualise only long tables: short ones (自选, the 88-row 排行) render faster and simpler as plain rows.
  const virtual = rows.length > VIRTUALIZE_ABOVE
  const virtualizer = useVirtualizer({
    count: virtual ? rows.length : 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  })
  const items = virtual
    ? virtualizer.getVirtualItems()
    : rows.map((_, index) => ({ index, start: index * rowHeight, end: (index + 1) * rowHeight }))
  const padTop = virtual && items.length ? items[0].start : 0
  const padBottom = virtual && items.length ? virtualizer.getTotalSize() - items[items.length - 1].end : 0
  const colSpan = table.getVisibleLeafColumns().length

  return (
    <div ref={parentRef} className="relative overflow-auto rounded-md border border-line bg-panel" style={{ maxHeight: height }}>
      <table className="w-full border-separate border-spacing-0 text-[13px]" aria-label={label}>
        <thead className="sticky top-0 z-10 bg-panel">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header, index) => {
                const meta = header.column.columnDef.meta
                const sorted = header.column.getIsSorted()
                const sortable = header.column.getCanSort()
                return (
                  <th
                    key={header.id}
                    scope="col"
                    style={{ width: meta?.width }}
                    aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                    className={cn(
                      'h-8 border-b border-line px-3 text-[12px] font-medium whitespace-nowrap text-subtle',
                      meta?.numeric ? 'text-right' : 'text-left',
                      index === 0 && 'sticky left-0 z-20 bg-panel',
                    )}
                  >
                    {header.isPlaceholder ? null : sortable ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className={cn('inline-flex cursor-pointer items-center gap-1 hover:text-fg', meta?.numeric && 'flex-row-reverse', sorted && 'text-fg')}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === 'asc' ? <ArrowUp className="h-3 w-3" /> : sorted === 'desc' ? <ArrowDown className="h-3 w-3" /> : null}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={colSpan} className="py-10 text-center text-muted">
                {emptyText}
              </td>
            </tr>
          )}
          {padTop > 0 && (
            <tr aria-hidden>
              <td colSpan={colSpan} style={{ height: padTop }} />
            </tr>
          )}
          {items.map((item) => {
            const row = rows[item.index]
            return (
              <tr
                key={row.id}
                data-index={item.index}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                onKeyDown={onRowClick ? (e) => e.key === 'Enter' && onRowClick(row.original) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                style={{ height: rowHeight }}
                className={cn('group', onRowClick && 'cursor-pointer')}
              >
                {row.getVisibleCells().map((cell, index) => (
                  <td
                    key={cell.id}
                    className={cn(
                      'border-b border-line px-3 whitespace-nowrap group-last:border-b-0 group-hover:bg-raised',
                      cell.column.columnDef.meta?.numeric ? 'num text-right' : 'text-left',
                      index === 0 && 'sticky left-0 bg-panel',
                    )}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            )
          })}
          {padBottom > 0 && (
            <tr aria-hidden>
              <td colSpan={colSpan} style={{ height: padBottom }} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

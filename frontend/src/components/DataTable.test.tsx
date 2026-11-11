import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ColumnDef } from '@tanstack/react-table'
import { describe, expect, it, vi } from 'vitest'
import { DataTable } from './DataTable'

interface Row {
  name: string
  change: number | null
}

const columns: ColumnDef<Row, unknown>[] = [
  { accessorKey: 'name', header: '名称' },
  { accessorKey: 'change', header: '涨跌幅', meta: { numeric: true }, sortUndefined: 'last' },
]

const data: Row[] = [
  { name: '甲', change: 1.5 },
  { name: '乙', change: -2 },
  { name: '丙', change: 3.2 },
]

function names() {
  return screen.getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[0]?.textContent)
}

describe('DataTable', () => {
  it('renders rows and sorts by header click (descending first)', () => {
    render(<DataTable label="测试表" data={data} columns={columns} />)
    expect(names()).toEqual(['甲', '乙', '丙'])
    fireEvent.click(screen.getByRole('button', { name: /涨跌幅/ }))
    expect(names()).toEqual(['丙', '甲', '乙'])
    expect(screen.getByRole('columnheader', { name: /涨跌幅/ })).toHaveAttribute('aria-sort', 'descending')
    fireEvent.click(screen.getByRole('button', { name: /涨跌幅/ }))
    expect(names()).toEqual(['乙', '甲', '丙'])
  })

  it('reports row clicks and shows the empty text', () => {
    const onRowClick = vi.fn()
    const { unmount } = render(<DataTable label="测试表" data={data} columns={columns} onRowClick={onRowClick} />)
    fireEvent.click(screen.getByText('乙'))
    expect(onRowClick).toHaveBeenCalledWith(data[1])
    unmount()
    render(<DataTable label="空表" data={[]} columns={columns} emptyText="没有自选股" />)
    expect(screen.getByText('没有自选股')).toBeInTheDocument()
  })

  it('right-aligns numeric columns', () => {
    render(<DataTable label="测试表" data={data} columns={columns} />)
    expect(screen.getByText('1.5').closest('td')).toHaveClass('text-right', 'num')
  })
})

/** Descriptive statistics for the 数据明细 summary — same definitions as pandas `describe()`. */
import { isNum } from './format'

export interface Describe {
  count: number
  mean: number
  std: number | null // sample standard deviation (n − 1); null with fewer than two values
  min: number
  q25: number
  median: number
  q75: number
  max: number
}

/** Linear-interpolation quantile on an ascending array (pandas default). */
function quantile(sorted: number[], q: number): number {
  const position = (sorted.length - 1) * q
  const low = Math.floor(position)
  const high = Math.ceil(position)
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low)
}

export function describe(values: (number | null | undefined)[]): Describe | null {
  const sorted = values.filter(isNum).sort((a, b) => a - b)
  const count = sorted.length
  if (count === 0) return null
  const mean = sorted.reduce((sum, v) => sum + v, 0) / count
  const std = count > 1 ? Math.sqrt(sorted.reduce((sum, v) => sum + (v - mean) ** 2, 0) / (count - 1)) : null
  return { count, mean, std, min: sorted[0], q25: quantile(sorted, 0.25), median: quantile(sorted, 0.5), q75: quantile(sorted, 0.75), max: sorted[count - 1] }
}

export const DESCRIBE_ROWS: { key: Exclude<keyof Describe, 'count'>; label: string }[] = [
  { key: 'mean', label: '平均值' },
  { key: 'std', label: '标准差' },
  { key: 'min', label: '最小值' },
  { key: 'q25', label: '25% 分位数' },
  { key: 'median', label: '中位数' },
  { key: 'q75', label: '75% 分位数' },
  { key: 'max', label: '最大值' },
]

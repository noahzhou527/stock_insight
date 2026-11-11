/** Thin typed fetch wrapper. DTO types come from schema.d.ts (generated from the backend OpenAPI). */
import type { components } from './schema'

export type Schemas = components['schemas']
export type Meta = Schemas['Meta']
export type ErrorInfo = Schemas['ErrorInfo']

export class ApiError extends Error {
  readonly status: number
  readonly info: ErrorInfo

  constructor(status: number, info: ErrorInfo) {
    super(info.message)
    this.status = status
    this.info = info
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

function url(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

async function request<T>(method: string, path: string, query?: Query, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(url(path, query), {
      method,
      signal,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError(0, { category: 'backend_unreachable', message: '无法连接本机后端，请确认服务已启动', detail: String(error) })
  }
  if (response.ok) return (await response.json()) as T
  let info: ErrorInfo = { category: 'http_error', message: `请求失败（HTTP ${response.status}）`, detail: null }
  try {
    const payload = await response.json()
    if (payload?.error?.message) info = payload.error
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(response.status, info)
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>('GET', path, query, undefined, signal),
  post: <T>(path: string, body: unknown) => request<T>('POST', path, undefined, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, undefined, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

/** `/api/instruments/US/%5EGSPC` — symbols such as ^GSPC or BRK-B are URL-encoded. */
export function instrumentPath(market: string, symbol: string, suffix = ''): string {
  return `/api/instruments/${market}/${encodeURIComponent(symbol)}${suffix}`
}

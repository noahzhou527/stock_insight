import { useEffect, useState } from 'react'

type Health = { status: string; time: string; providers: { name: string }[] }

// P0 骨架：只验证前端能经由 Vite 代理访问后端。P3 起替换为正式页面。
export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setHealth)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <main style={{ padding: 16 }}>
      <h1 style={{ fontSize: 18, margin: '0 0 8px' }}>Stock Insight</h1>
      {error && <p style={{ color: 'var(--text-2)' }}>后端不可用：{error}</p>}
      {health && (
        <p style={{ color: 'var(--text-2)' }}>
          后端状态：{health.status} · 数据源：{health.providers.map((p) => p.name).join(' / ')}
        </p>
      )}
      {!health && !error && <p style={{ color: 'var(--text-2)' }}>正在连接后端…</p>}
    </main>
  )
}

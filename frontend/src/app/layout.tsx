import { Link, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, type Schemas } from '@/lib/api'

/** 全局顶栏(页面清单 §1):标识 + 项目切换器 + 复习入口(角标=到期数);设置 M5 */
export function RootLayout() {
  const navigate = useNavigate()
  const { data: studies } = useQuery({
    queryKey: ['studies'],
    queryFn: () => api<Schemas['StudyOut'][]>('/api/studies?include_archived=false'),
  })
  const { data: due } = useQuery({
    queryKey: ['review-count'],
    queryFn: () => api<Schemas['CardOut'][]>('/api/review/queue'),
    refetchInterval: 60_000,
  })
  const current = location.pathname.match(/^\/studies\/(\d+)/)?.[1]

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 flex h-14 items-center gap-4 border-b bg-background px-6">
        <Link to="/" className="text-lg font-semibold tracking-tight">
          BetterOneself
        </Link>
        <select
          className="h-8 rounded-md border bg-transparent px-2 text-sm"
          value={current ?? ''}
          onChange={(e) => e.target.value && navigate(`/studies/${e.target.value}/sources`)}
        >
          <option value="">选择项目…</option>
          {(studies ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <Link
          to="/review"
          className="ml-auto flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/50"
          data-testid="review-entry"
        >
          复习
          {(due?.length ?? 0) > 0 && (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-xs text-primary-foreground">
              {due!.length}
            </span>
          )}
        </Link>
        <Link
          to="/settings"
          className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/50"
          data-testid="settings-entry"
        >
          设置
        </Link>
      </header>
      <Outlet />
    </div>
  )
}

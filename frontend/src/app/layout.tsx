import { Link, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, type Schemas } from '@/lib/api'

/** 全局顶栏(页面清单 §1):标识 + 项目切换器;复习入口/设置随后续里程碑补 */
export function RootLayout() {
  const navigate = useNavigate()
  const { data: studies } = useQuery({
    queryKey: ['studies'],
    queryFn: () => api<Schemas['StudyOut'][]>('/api/studies?include_archived=false'),
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
      </header>
      <Outlet />
    </div>
  )
}

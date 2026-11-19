import { NavLink, Outlet, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, type Schemas } from '@/lib/api'

// tab 次序=用户旅程(页面清单 §1):资料→知识点→计划→卡片→档案→摘要(复习是全局页)
const TABS = [
  { to: 'sources', label: '资料' },
  { to: 'knowledge', label: '知识点' },
  { to: 'plan', label: '计划' },
  { to: 'cards', label: '卡片' },
  { to: 'mastery', label: '档案' },
  { to: 'summaries', label: '摘要' },
]

/** 项目内布局:项目名 + 左侧 tab + 内容区 */
export function StudyLayout() {
  const { id } = useParams()
  const { data: study } = useQuery({
    queryKey: ['study', id],
    queryFn: () => api<Schemas['StudyOut']>(`/api/studies/${id}`),
  })

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)]">
      <aside className="w-52 shrink-0 border-r p-4">
        <div className="mb-4">
          <div className="font-medium">{study?.name ?? '…'}</div>
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{study?.goal}</div>
        </div>
        <nav className="space-y-1">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                `block rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/50'}`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-6">
        <Outlet />
      </main>
    </div>
  )
}

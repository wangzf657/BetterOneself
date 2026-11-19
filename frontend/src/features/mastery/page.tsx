import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FileDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'

interface MasteryEvent {
  id: number
  from_status: string | null
  to_status: string
  evidence_type: string
  evidence_id: string
  created_at: string
}

interface MasteryKp {
  id: number
  parent_id: number | null
  name: string
  kp_type: string
  mastery_status: string
  self_reported: string
  events: MasteryEvent[]
}

const STATUS_BADGE: Record<
  string,
  { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  new: { label: '未学', variant: 'outline' },
  learning: { label: '学习中', variant: 'secondary' },
  passed: { label: '已通过', variant: 'default' },
  weak: { label: '薄弱', variant: 'destructive' },
}

/** 掌握档案(M6-01/02/03):知识点树+状态整全视图,自评与系统评估并列,证据链抽屉 */
export function MasteryPage() {
  const { id: studyId } = useParams()
  const [filter, setFilter] = useState('')
  const [openKp, setOpenKp] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['mastery', studyId],
    queryFn: () => api<{ kps: MasteryKp[] }>(`/api/studies/${studyId}/mastery`),
  })

  if (isLoading) return <Skeleton className="h-96 w-full" />
  const kps = (data?.kps ?? []).filter((k) => !filter || k.mastery_status === filter)
  const counts = (data?.kps ?? []).reduce<Record<string, number>>((acc, k) => {
    acc[k.mastery_status] = (acc[k.mastery_status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">掌握档案</h1>
        <select
          className="ml-auto h-8 rounded-md border bg-transparent px-2 text-sm"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="按状态筛选"
        >
          <option value="">全部({data?.kps.length ?? 0})</option>
          {Object.entries(STATUS_BADGE).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}({counts[value] ?? 0})
            </option>
          ))}
        </select>
        <a
          href={`/api/studies/${studyId}/report.md`}
          download
          onClick={(e) => e.preventDefault()}
          className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent/50"
        >
          <FileDown size={14} /> 导出学习报告
        </a>
      </div>

      <div className="space-y-1" data-testid="mastery-list">
        {kps.map((k) => {
          const badge = STATUS_BADGE[k.mastery_status] ?? STATUS_BADGE.new
          return (
            <div key={k.id} className="rounded-md border">
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent/40"
                onClick={() => setOpenKp(openKp === k.id ? null : k.id)}
              >
                {k.events.length > 0 ? (
                  openKp === k.id ? (
                    <ChevronDown size={15} />
                  ) : (
                    <ChevronRight size={15} />
                  )
                ) : (
                  <span className="inline-block w-4" />
                )}
                <span className="min-w-0 flex-1 truncate text-sm">{k.name}</span>
                {/* 自评与系统评估两列并列(M6-03) */}
                {k.self_reported === 'mastered' && (
                  <Badge variant="outline" className="border-sky-400/60 text-[10px] text-sky-600">
                    自评:已掌握
                  </Badge>
                )}
                <Badge variant={badge.variant} className="text-[10px]">
                  {badge.label}
                </Badge>
              </button>
              {openKp === k.id && k.events.length > 0 && (
                <div
                  className="space-y-1 border-t px-6 py-2 text-xs text-muted-foreground"
                  data-testid={`evidence-${k.id}`}
                >
                  <p className="font-medium text-foreground">证据链</p>
                  {k.events.map((e) => (
                    <p key={e.id}>
                      {e.created_at.slice(0, 16).replace('T', ' ')} ·{' '}
                      {e.evidence_type === 'quiz' ? '测验' : '复习'} #{e.evidence_id}:{' '}
                      {e.from_status ?? '—'} →{' '}
                      <span className="text-foreground">{e.to_status}</span>
                    </p>
                  ))}
                </div>
              )}
            </div>
          )
        })}
        {kps.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            还没有知识点。先到
            <Link to={`/studies/${studyId}/sources`} className="mx-1 underline">
              资料
            </Link>
            页导入。
          </p>
        )}
      </div>
    </div>
  )
}

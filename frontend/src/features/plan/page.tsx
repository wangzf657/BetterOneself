import { useMemo } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type Schemas } from '@/lib/api'

const TASK_TYPE_LABEL: Record<string, string> = {
  learn: '学习',
  review_weak: '薄弱点复习',
  feynman: '费曼',
  quiz: '测验',
}

/** 计划页(M2-05/06, M5-02):按日分组、移动改期、确认生效、超限警示、重排历史 */
export function PlanPage() {
  const { id: studyId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: plan, isLoading } = useQuery({
    queryKey: ['plan', studyId],
    queryFn: () => api<Schemas['PlanDetail']>(`/api/studies/${studyId}/plan`),
    retry: false,
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['plan', studyId] })

  const confirm = useMutation({
    mutationFn: (id: number) =>
      api<Schemas['PlanDetail']>(`/api/plans/${id}/confirm`, { method: 'POST' }),
    onSuccess: () => {
      toast.success('计划已生效,今日任务已生成')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const move = useMutation({
    mutationFn: ({ id, date }: { id: number; date: string }) =>
      api<Schemas['TaskOut']>(`/api/tasks/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ scheduled_date: date }),
      }),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error(e.message),
  })

  const byDay = useMemo(() => {
    const groups = new Map<string, Schemas['TaskOut'][]>()
    for (const t of plan?.tasks ?? []) {
      const list = groups.get(t.scheduled_date) ?? []
      list.push(t)
      groups.set(t.scheduled_date, list)
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [plan])

  if (isLoading) return <Skeleton className="h-96 w-full" />

  if (!plan) {
    return (
      <div className="mx-auto max-w-xl rounded-lg border p-10 text-center">
        <p className="text-sm text-muted-foreground">还没有计划。先做一次目标访谈。</p>
        <Button className="mt-4" onClick={() => navigate(`/studies/${studyId}/plan/interview`)}>
          开始目标访谈
        </Button>
      </div>
    )
  }

  const isDraft = plan.status === 'draft'

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">学习计划</h1>
        <Badge variant={isDraft ? 'secondary' : 'default'}>{isDraft ? '草案' : '已生效'}</Badge>
        <span className="ml-auto text-sm text-muted-foreground">
          每日 {plan.daily_minutes} 分钟
          {plan.deadline ? ` · 期限 ${plan.deadline}` : ''}
        </span>
        {isDraft && (
          <Button onClick={() => confirm.mutate(plan.id)} disabled={confirm.isPending}>
            {confirm.isPending ? '生效中…' : '确认生效'}
          </Button>
        )}
      </div>

      {plan.warning && (
        <Card className="border-amber-400/60 bg-amber-50/50 dark:bg-amber-950/20">
          <CardContent className="py-3 text-sm text-amber-700 dark:text-amber-400">
            {plan.warning}
          </CardContent>
        </Card>
      )}

      <div className="space-y-4" data-testid="plan-days">
        {byDay.map(([day, tasks]) => (
          <div key={day} data-testid={`plan-day-${day}`}>
            <div className="mb-1.5 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              {day}
              <span className="text-xs font-normal">
                共 {tasks.reduce((s, t) => s + t.estimated_minutes, 0)} 分钟
              </span>
            </div>
            {tasks.map((t) => (
              <TaskRow key={t.id} task={t} onMove={(d) => move.mutate({ id: t.id, date: d })} />
            ))}
          </div>
        ))}
        {plan.tasks.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            计划为空——先到
            <Link to={`/studies/${studyId}/knowledge`} className="mx-1 underline">
              知识点
            </Link>
            页确认拆解结果。
          </p>
        )}
      </div>

      {plan.events.length > 0 && (
        <div className="space-y-1.5 rounded-lg border p-4" data-testid="plan-events">
          <h2 className="text-sm font-medium">变更历史</h2>
          {plan.events.map((e) => (
            <div key={e.id} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>
                {e.event_type === 'generated'
                  ? '生成草案'
                  : e.event_type === 'confirmed'
                    ? '确认生效'
                    : e.event_type === 'adjusted'
                      ? '手动调整'
                      : '逾期重排'}
              </span>
              <span>{e.created_at.slice(0, 16).replace('T', ' ')}</span>
              {e.event_type === 'rescheduled' && (
                <span className="line-clamp-1 flex-1 truncate">
                  {(() => {
                    try {
                      const detail = JSON.parse(e.detail_json) as {
                        tasks?: { from: string; to: string }[]
                      }
                      return `${detail.tasks?.length ?? 0} 个任务已重排`
                    } catch {
                      return ''
                    }
                  })()}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function TaskRow({ task, onMove }: { task: Schemas['TaskOut']; onMove: (date: string) => void }) {
  return (
    <div
      className="flex items-center gap-2 rounded-md border px-3 py-2"
      data-testid={`task-${task.id}`}
    >
      <Badge variant="outline">{TASK_TYPE_LABEL[task.task_type] ?? task.task_type}</Badge>
      <span className="min-w-0 flex-1 truncate text-sm">{task.kp_name}</span>
      <span className="text-xs text-muted-foreground">{task.estimated_minutes} 分钟</span>
      <span className="text-xs text-muted-foreground">
        {task.status === 'done' ? '已完成' : task.status === 'skipped' ? '已跳过' : ''}
      </span>
      {task.status === 'pending' && (
        <Input
          type="date"
          className="h-7 w-36 text-xs"
          value={task.scheduled_date}
          onChange={(e) => e.target.value && onMove(e.target.value)}
          aria-label={`移动 ${task.kp_name} 到`}
        />
      )}
    </div>
  )
}

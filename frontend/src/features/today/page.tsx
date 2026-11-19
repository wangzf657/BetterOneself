import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type Schemas } from '@/lib/api'

const TASK_TYPE_LABEL: Record<string, string> = {
  learn: '学习',
  review_weak: '薄弱点复习',
  feynman: '费曼',
  quiz: '测验',
}

/** 今日任务页(M5-01/02/04/06):首页即今日任务;逾期横幅、复习入口、薄弱点标识、回炉询问 */
export function TodayPage() {
  const queryClient = useQueryClient()
  const { data: today, isLoading } = useQuery({
    queryKey: ['today'],
    queryFn: () => api<Schemas['TodayOut']>('/api/today'),
    // 今日页是惰性重排的触发点,切回来时重新执行
    refetchOnWindowFocus: true,
  })
  const { data: studies } = useQuery({
    queryKey: ['studies'],
    queryFn: () => api<Schemas['StudyOut'][]>('/api/studies'),
  })
  const firstStudy = studies?.[0]
  const { data: inactivity } = useQuery({
    queryKey: ['inactivity', firstStudy?.id],
    queryFn: () =>
      api<{ inactive_days: number; suggest_reset: boolean }>(
        `/api/studies/${firstStudy!.id}/inactivity`,
      ),
    enabled: !!firstStudy,
  })

  const resettle = useMutation({
    mutationFn: () =>
      api<{ tasks_rescheduled: number; weak_cards_pulled: number }>(
        `/api/studies/${firstStudy!.id}/return-from-break`,
        { method: 'POST' },
      ),
    onSuccess: (r) => {
      toast.success(
        `回炉完成:${r.tasks_rescheduled} 个任务已重排,${r.weak_cards_pulled} 张薄弱卡提到今天`,
      )
      void queryClient.invalidateQueries({ queryKey: ['today'] })
      void queryClient.invalidateQueries({ queryKey: ['inactivity'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (isLoading) return <Skeleton className="mx-auto mt-10 h-96 w-full max-w-3xl" />

  const view = today
  const active = studies ?? []
  const noPlan = active.length > 0 && view?.has_plan === false

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">今天该做什么</h1>
        <p className="text-sm text-muted-foreground">{view?.date}</p>
      </div>

      {/* 逾期重排横幅(M5-02) */}
      {(view?.rescheduled.length ?? 0) > 0 && (
        <Card
          className="border-amber-400/60 bg-amber-50/50 dark:bg-amber-950/20"
          data-testid="reschedule-banner"
        >
          <CardContent className="py-3 text-sm text-amber-700 dark:text-amber-400">
            以下 {view!.rescheduled.length} 个逾期任务已重排进未来日程(不堆积):
            <ul className="mt-1 space-y-0.5 text-xs">
              {view!.rescheduled.slice(0, 5).map((r) => (
                <li key={r.task_id}>
                  {r.kp_id}:{r.from} → {r.to}
                </li>
              ))}
              {view!.rescheduled.length > 5 && <li>…等 {view!.rescheduled.length - 5} 个</li>}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* 到期复习入口(M4-01) */}
      {(view?.due_reviews ?? 0) > 0 && (
        <Link to="/review" className="block">
          <Card className="transition-colors hover:bg-accent/40" data-testid="due-reviews-entry">
            <CardContent className="flex items-center gap-3 py-4">
              <span className="inline-flex h-8 min-w-8 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground">
                {view!.due_reviews}
              </span>
              <span className="text-sm">张卡片今天到期——先清复习(3-10 分钟)</span>
              <span className="ml-auto text-xs text-muted-foreground">去复习 →</span>
            </CardContent>
          </Card>
        </Link>
      )}

      {/* 中断回炉询问(M5-06) */}
      {inactivity?.suggest_reset && (
        <Card
          className="border-amber-400/60 bg-amber-50/50 dark:bg-amber-950/20"
          data-testid="resettle-banner"
        >
          <CardContent className="flex items-center gap-3 py-3 text-sm text-amber-700 dark:text-amber-400">
            <span className="flex-1">
              你已经 {inactivity.inactive_days}{' '}
              天没有学习了。要把剩余计划重排到今天起、并把高风险薄弱卡片提到今天吗?
            </span>
            <Button size="sm" onClick={() => resettle.mutate()} disabled={resettle.isPending}>
              {resettle.isPending ? '回炉中…' : '回炉重排'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* 今日任务列表 */}
      <div className="space-y-2" data-testid="today-tasks">
        {(view?.tasks ?? []).map((t) => (
          <TodayTaskRow key={t.id} task={t} />
        ))}
        {(view?.tasks.length ?? 0) === 0 && view?.has_plan && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            今日任务已清空。去看看复习队列或资料。
          </p>
        )}
        {(view?.tasks.length ?? 0) === 0 && !view?.has_plan && active.length > 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">今天没有安排的任务。</p>
        )}
      </div>

      {/* 空态引导 */}
      {active.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center">
            <p className="mb-4 text-sm text-muted-foreground">还没有学习项目——从一个开始。</p>
            <Link
              to="/studies"
              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
            >
              去创建
            </Link>
          </CardContent>
        </Card>
      ) : (
        noPlan && (
          <Card>
            <CardContent className="py-6 text-center text-sm text-muted-foreground">
              <NoPlanHint studyId={String(active[0].id)} />
            </CardContent>
          </Card>
        )
      )}
    </main>
  )
}

/** 单条今日任务:类型徽标、薄弱点标识+证据、点击进入会话并完成 */
function TodayTaskRow({ task }: { task: Schemas['TaskOut'] }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const complete = useMutation({
    mutationFn: () => api<Schemas['TaskOut']>(`/api/tasks/${task.id}/complete`, { method: 'POST' }),
    onSuccess: () => {
      toast.success(`已完成「${task.kp_name}」`)
      void queryClient.invalidateQueries({ queryKey: ['today'] })
    },
  })

  const start = () => {
    // 进会话(先建会话再跳转,页面清单 §3):会话页内可提问+测验
    api<Schemas['SessionOut']>(`/api/studies/${task.study_id}/sessions`, {
      method: 'POST',
      body: JSON.stringify({ kp_id: task.kp_id, task_id: task.id }),
    })
      .then((s) => navigate(`/studies/${task.study_id}/learn/${s.id}`))
      .catch((e: Error) => toast.error(e.message))
  }

  return (
    <Card className="group" data-testid={`today-task-${task.id}`}>
      <CardContent className="flex items-center gap-3 py-3">
        <Badge variant="outline">{TASK_TYPE_LABEL[task.task_type] ?? task.task_type}</Badge>
        <button
          type="button"
          onClick={start}
          className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline"
        >
          {task.kp_name}
        </button>
        {task.task_type === 'review_weak' && task.weak_evidence_id && (
          <Badge
            variant="destructive"
            className="text-[10px]"
            title={`证据:${task.weak_evidence_id}`}
          >
            针对薄弱点
          </Badge>
        )}
        <span className="text-xs text-muted-foreground">{task.estimated_minutes} 分钟</span>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => complete.mutate()}
          disabled={complete.isPending}
        >
          完成
        </Button>
      </CardContent>
    </Card>
  )
}

function NoPlanHint({ studyId }: { studyId: string }) {
  const navigate = useNavigate()
  return (
    <>
      项目还没有生效的学习计划。做一次
      <button
        type="button"
        className="mx-1 underline"
        onClick={() => navigate(`/studies/${studyId}/plan/interview`)}
      >
        目标访谈
      </button>
      让计划跑起来。
    </>
  )
}

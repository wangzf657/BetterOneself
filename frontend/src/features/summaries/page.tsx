import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'

interface SummaryItem {
  id: number
  summary_type: string
  period_date: string
  content_md: string
}

/** 摘要与复盘(M5-03/05):每日摘要 + 周复盘列表(建议需确认,不自动改计划) */
export function SummariesPage() {
  const { id: studyId } = useParams()
  const { data: summaries, isLoading } = useQuery({
    queryKey: ['summaries', studyId],
    queryFn: () => api<SummaryItem[]>(`/api/studies/${studyId}/summaries`),
  })

  if (isLoading) return <Skeleton className="h-96 w-full" />
  const daily = (summaries ?? []).filter((s) => s.summary_type === 'daily')
  const weekly = (summaries ?? []).filter((s) => s.summary_type === 'weekly')

  return (
    <div className="mx-auto max-w-3xl space-y-8" data-testid="summaries-page">
      <section>
        <h1 className="mb-4 text-2xl font-semibold">摘要与复盘</h1>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">本周复盘</h2>
        {weekly.length === 0 && (
          <p className="text-sm text-muted-foreground">本周还没有复盘数据。</p>
        )}
        {weekly.map((s) => (
          <SummaryCard key={s.id} item={s} />
        ))}

        <h2 className="mt-6 mb-2 text-sm font-medium text-muted-foreground">每日摘要</h2>
        {daily.length === 0 && (
          <p className="text-sm text-muted-foreground">当天有学习行为后自动生成摘要;今天还没有。</p>
        )}
        {daily.map((s) => (
          <SummaryCard key={s.id} item={s} />
        ))}
      </section>
    </div>
  )
}

function SummaryCard({ item }: { item: SummaryItem }) {
  return (
    <div className="mb-3 rounded-lg border p-4">
      <div className="mb-2 text-xs text-muted-foreground">
        {item.summary_type === 'weekly' ? '周复盘' : '每日摘要'} · {item.period_date}
        {item.summary_type === 'weekly' && (
          <span className="ml-2">(调整建议需到计划页确认后手动执行)</span>
        )}
      </div>
      <pre className="whitespace-pre-wrap font-sans text-sm">{item.content_md}</pre>
    </div>
  )
}

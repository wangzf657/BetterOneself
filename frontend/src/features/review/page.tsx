import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type Schemas } from '@/lib/api'

const RATINGS = [
  { value: 1, label: '忘了', hint: '1' },
  { value: 2, label: '困难', hint: '2' },
  { value: 3, label: '良好', hint: '3' },
  { value: 4, label: '轻松', hint: '4' },
]

/** 复习页(页面清单 #9/§3):单卡流零跳转,键盘完成全部操作;碎片模式 3-10 分钟 */
export function ReviewPage() {
  const { data: queue, isLoading } = useQuery({
    queryKey: ['review-queue'],
    queryFn: () => api<Schemas['CardOut'][]>('/api/review/queue'),
  })
  const { data: params } = useQuery({
    queryKey: ['review-params'],
    queryFn: () => api<{ desired_retention: number; parameters: number[] }>('/api/review/params'),
  })

  const [flipped, setFlipped] = useState(false)
  const [doneIds, setDoneIds] = useState<number[]>([])
  const [requeuedIds, setRequeuedIds] = useState<number[]>([])

  // "忘了"的卡挪队尾当日重现(M4-02);纯派生,不用 effect 同步
  const remaining = useMemo(() => {
    if (!queue) return []
    const requeued = new Set(requeuedIds)
    const ordered = [
      ...queue.filter((c) => !requeued.has(c.id)),
      ...queue.filter((c) => requeued.has(c.id)),
    ]
    return ordered.filter((c) => !doneIds.includes(c.id))
  }, [queue, requeuedIds, doneIds])

  const current = remaining[0]
  const total = queue?.length ?? 0
  const finished = total > 0 && remaining.length === 0

  const rate = useMutation({
    mutationFn: ({ id, rating }: { id: number; rating: number }) =>
      api<Schemas['CardOut']>(`/api/cards/${id}/rate`, {
        method: 'POST',
        body: JSON.stringify({ rating }),
      }),
  })

  const doRate = useCallback(
    (rating: number) => {
      if (!current || !flipped || rate.isPending) return
      const id = current.id
      rate.mutate(
        { id, rating },
        {
          onSuccess: () => {
            setFlipped(false)
            if (rating === 1) {
              setRequeuedIds((ids) => [...ids, id])
            } else {
              setDoneIds((ids) => [...ids, id])
              if (remaining.length === 1) toast.success('今日复习完成 🎉')
            }
          },
        },
      )
    },
    [current, flipped, rate, remaining.length],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setFlipped((f) => !f)
      } else if (['1', '2', '3', '4'].includes(e.key)) {
        doRate(Number(e.key))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [doRate])

  if (isLoading) return <Skeleton className="mx-auto mt-16 h-64 w-full max-w-xl" />

  if (total === 0 || finished) {
    return (
      <main className="mx-auto max-w-xl p-16 text-center">
        <p className="text-lg font-medium">{finished ? '今日复习完成 🎉' : '今日无复习'}</p>
        <p className="mt-2 text-sm text-muted-foreground">队列空了,去看看今日任务。</p>
        <Link
          to="/"
          className="mt-6 inline-block rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
        >
          回首页
        </Link>
      </main>
    )
  }

  return (
    <main
      className="mx-auto flex max-w-xl flex-col items-center px-6 pt-10"
      data-testid="review-page"
    >
      <div className="mb-4 flex w-full items-center justify-between text-sm text-muted-foreground">
        <span data-testid="review-progress">
          {doneIds.length + 1} / {total}
        </span>
        {params && (
          <span className="text-xs" title={`FSRS 参数(${params.parameters.length} 个)可查看`}>
            目标留存率 {(params.desired_retention * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <Card
        className="w-full cursor-pointer select-none"
        onClick={() => setFlipped((f) => !f)}
        data-testid="review-card"
      >
        <CardContent className="flex min-h-64 flex-col items-center justify-center gap-4 p-8 text-center">
          <div className="text-lg font-medium">{current.front}</div>
          {flipped ? (
            <div className="space-y-3">
              <div className="prose prose-sm dark:prose-invert max-w-none text-left">
                <Markdown remarkPlugins={[remarkGfm]}>{current.back_md}</Markdown>
              </div>
              {current.source_id && current.chunk_id && (
                <Link
                  to={`/studies/0/sources/${current.source_id}?chunk=${current.chunk_id}`}
                  className="block text-xs text-muted-foreground underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  查看源文
                </Link>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">空格 / 点击翻面</p>
          )}
        </CardContent>
      </Card>

      {flipped && (
        <div className="mt-5 flex w-full gap-2" data-testid="rating-bar">
          {RATINGS.map((r) => (
            <Button
              key={r.value}
              variant={r.value === 1 ? 'destructive' : 'outline'}
              className="flex-1"
              disabled={rate.isPending}
              onClick={() => doRate(r.value)}
            >
              {r.hint} {r.label}
            </Button>
          ))}
        </div>
      )}
    </main>
  )
}

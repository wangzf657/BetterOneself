import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { api, type Schemas } from '@/lib/api'

type QuizItem = Schemas['QuizOut']

/** 会话内嵌测验(M3-04/05):出题、作答、即时反馈、错题回看源文 */
export function QuizPanel({ sessionId, studyId }: { sessionId: number; studyId: number }) {
  const queryClient = useQueryClient()
  const [shortAnswers, setShortAnswers] = useState<Record<number, string>>({})

  const { data: quizzes, isLoading } = useQuery({
    queryKey: ['quizzes', sessionId],
    queryFn: () => api<QuizItem[]>(`/api/sessions/${sessionId}/quizzes`),
  })

  const generate = useMutation({
    mutationFn: () =>
      api<Schemas['QuizPending'][]>(`/api/sessions/${sessionId}/quizzes`, { method: 'POST' }),
    onSuccess: (rows) => {
      toast.success(`已出 ${rows.length} 道题`)
      void queryClient.invalidateQueries({ queryKey: ['quizzes', sessionId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const answer = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) =>
      api<QuizItem>(`/api/quizzes/${id}/answer`, {
        method: 'POST',
        body: JSON.stringify({ answer: text }),
      }),
    onSuccess: (graded) => {
      if (!graded.is_correct) toast.info('已生成 1 张复习卡片,稍后到复习队列见') // M3-05
      void queryClient.invalidateQueries({ queryKey: ['quizzes', sessionId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (isLoading) return <Skeleton className="h-24 w-full" />

  return (
    <div className="space-y-3">
      {quizzes?.length === 0 && (
        <Card>
          <CardContent className="flex items-center justify-between py-4">
            <span className="text-sm text-muted-foreground">学完了?测一测才算掌握。</span>
            <Button size="sm" onClick={() => generate.mutate()} disabled={generate.isPending}>
              {generate.isPending ? '出题中…' : '考我一组'}
            </Button>
          </CardContent>
        </Card>
      )}
      {(quizzes ?? []).map((q) => {
        const answered = q.user_answer !== null && q.user_answer !== undefined
        return (
          <Card key={q.id} data-testid={`quiz-${q.id}`}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <Badge variant="outline">{q.q_type === 'objective' ? '单选' : '简答'}</Badge>
                <span className="flex-1">{q.question}</span>
                {answered && (
                  <Badge variant={q.is_correct ? 'default' : 'destructive'}>
                    {q.is_correct ? '答对' : '答错'}
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {q.q_type === 'objective' &&
                (q.options ?? []).map((opt) => (
                  <Button
                    key={opt}
                    variant={answered ? (opt === q.answer ? 'default' : 'outline') : 'outline'}
                    size="sm"
                    className="mr-2"
                    disabled={answered || answer.isPending}
                    onClick={() => answer.mutate({ id: q.id, text: opt })}
                  >
                    {opt}
                  </Button>
                ))}
              {q.q_type === 'short_answer' && !answered && (
                <div className="flex gap-2">
                  <Input
                    placeholder="用自己的话回答…"
                    value={shortAnswers[q.id] ?? ''}
                    onChange={(e) => setShortAnswers((s) => ({ ...s, [q.id]: e.target.value }))}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (shortAnswers[q.id] ?? '').trim())
                        answer.mutate({ id: q.id, text: shortAnswers[q.id] })
                    }}
                  />
                  <Button
                    size="sm"
                    disabled={!(shortAnswers[q.id] ?? '').trim() || answer.isPending}
                    onClick={() => answer.mutate({ id: q.id, text: shortAnswers[q.id] })}
                  >
                    提交
                  </Button>
                </div>
              )}
              {answered && (
                <div className="space-y-1 text-sm">
                  <p className="text-muted-foreground">
                    你的回答:{q.user_answer}
                    {!q.is_correct && (
                      <>
                        {' '}
                        / 正确答案:<span className="text-foreground">{q.answer}</span>
                      </>
                    )}
                  </p>
                  {q.ai_feedback && <p className="text-xs">{q.ai_feedback}</p>}
                  {!q.is_correct && q.source_id && q.chunk_id && (
                    <Link
                      to={`/studies/${studyId}/sources/${q.source_id}?chunk=${q.chunk_id}`}
                      className="inline-block text-xs text-muted-foreground underline"
                    >
                      回看源文
                    </Link>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
      {(quizzes ?? []).length > 0 &&
        (quizzes ?? []).every((q) => q.user_answer !== null && q.user_answer !== undefined) && (
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="outline"
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
            >
              再来一组
            </Button>
          </div>
        )}
    </div>
  )
}

/** 对话卡壳点手动存卡(M3-05)。父组件以 key 控制重挂载来重置预填。 */
export function SaveCardForm({
  onDone,
  studyId,
  kpId,
  prefill,
}: {
  onDone: () => void
  studyId: number
  kpId: number | null
  prefill: string
}) {
  const [front, setFront] = useState('')
  const [back, setBack] = useState(prefill.slice(0, 500))

  const create = useMutation({
    mutationFn: () =>
      api<Schemas['CardOut']>(`/api/studies/${studyId}/cards`, {
        method: 'POST',
        body: JSON.stringify({ kp_id: kpId, front, back_md: back, origin: 'manual_mark' }),
      }),
    onSuccess: () => {
      toast.success('已存为复习卡片')
      onDone()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate()
      }}
    >
      <Input
        placeholder="正面:问题"
        value={front}
        onChange={(e) => setFront(e.target.value)}
        required
      />
      <Textarea
        placeholder="背面:答案/要点"
        value={back}
        onChange={(e) => setBack(e.target.value)}
        rows={4}
      />
      <Button type="submit" disabled={create.isPending || !front.trim() || kpId === null}>
        {kpId === null ? '会话未绑定知识点' : create.isPending ? '保存中…' : '保存'}
      </Button>
    </form>
  )
}

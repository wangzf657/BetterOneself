import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { api, type Schemas } from '@/lib/api'

/** 目标访谈(M2-04):三问表单;可跳过(用默认值并明示) */
export function InterviewPage() {
  const { id: studyId } = useParams()
  const navigate = useNavigate()
  const [depth, setDepth] = useState('')
  const [deadline, setDeadline] = useState('')
  const [minutes, setMinutes] = useState('45')

  const generate = useMutation({
    mutationFn: (payload: Partial<Schemas['PlanGenerateIn']> & { skipped?: boolean }) =>
      api<Schemas['PlanDetail']>(`/api/studies/${studyId}/plans`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => navigate(`/studies/${studyId}/plan`),
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="mb-2 text-2xl font-semibold">目标访谈</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        回答三个问题,好让计划贴合你的节奏。不想填可跳过,用默认值生成。
      </p>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">三个问题</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault()
              generate.mutate({
                goal_depth: depth || '标准理解',
                deadline: deadline || null,
                daily_minutes: Number(minutes) || 45,
                skipped: false,
              })
            }}
          >
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">① 学到什么程度?</span>
              <Input
                placeholder="如:能独立写 CLI 工具 / 应付面试 / 读懂源码"
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">② 什么时候完成?</span>
              <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </label>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">③ 每天能投入多少分钟?</span>
              <Input
                type="number"
                min={10}
                max={480}
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
              />
            </label>
            <div className="flex items-center justify-between pt-2">
              <Button
                type="button"
                variant="ghost"
                disabled={generate.isPending}
                onClick={() => generate.mutate({ skipped: true })}
                title="将使用默认值:目标「标准理解」,期限 30 天,每天 45 分钟"
              >
                跳过(用默认值)
              </Button>
              <Button type="submit" disabled={generate.isPending}>
                {generate.isPending ? '生成中…' : '生成计划草案'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

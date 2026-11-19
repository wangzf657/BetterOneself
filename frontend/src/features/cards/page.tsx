import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Pause, Play, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { api, type Schemas } from '@/lib/api'

const ORIGIN_LABEL: Record<string, string> = {
  auto_quiz: '错题',
  manual_mark: '手动标记',
  manual_new: '手建',
}

/** 卡片管理(M4-04/06):列表筛选、编辑(不动历史)、暂停/恢复、删除、Anki 导出 */
export function CardsPage() {
  const { id: studyId } = useParams()
  const queryClient = useQueryClient()
  const [kpFilter, setKpFilter] = useState('')
  const [editing, setEditing] = useState<Schemas['CardOut'] | null>(null)
  const [front, setFront] = useState('')
  const [back, setBack] = useState('')
  const [deleting, setDeleting] = useState<Schemas['CardOut'] | null>(null)

  const { data: cards, isLoading } = useQuery({
    queryKey: ['cards', studyId],
    queryFn: () =>
      api<Schemas['CardOut'][]>(
        `/api/studies/${studyId}/cards${kpFilter ? `?kp_id=${kpFilter}` : ''}`,
      ),
  })
  const { data: tree } = useQuery({
    queryKey: ['knowledge', studyId],
    queryFn: () => api<Schemas['KpNode'][]>(`/api/studies/${studyId}/knowledge`),
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['cards', studyId] })
    void queryClient.invalidateQueries({ queryKey: ['review-count'] })
  }

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api<Schemas['CardOut']>(`/api/cards/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: () => {
      setEditing(null)
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/api/cards/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      setDeleting(null)
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (isLoading) return <Skeleton className="h-96 w-full" />

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">卡片管理</h1>
        <select
          className="ml-auto h-8 rounded-md border bg-transparent px-2 text-sm"
          value={kpFilter}
          onChange={(e) => setKpFilter(e.target.value)}
        >
          <option value="">全部知识点</option>
          {(tree ?? []).map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </select>
        {/* Anki 导出(M4-06):浏览器直接下载 */}
        <a
          href={`/api/studies/${studyId}/cards/export.tsv`}
          className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent/50"
          onClick={(e) => e.preventDefault()}
          download
        >
          导出 Anki(TSV)
        </a>
      </div>

      <div className="space-y-2" data-testid="cards-list">
        {(cards ?? []).map((c) => (
          <Card key={c.id}>
            <CardContent className="flex items-center gap-3 py-3">
              <Badge variant="outline">{ORIGIN_LABEL[c.origin] ?? c.origin}</Badge>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{c.front}</p>
                <p className="truncate text-xs text-muted-foreground">{c.back_md}</p>
              </div>
              {c.status === 'suspended' && (
                <Badge variant="secondary" className="text-[10px]">
                  已暂停
                </Badge>
              )}
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                aria-label={c.status === 'suspended' ? `恢复 ${c.front}` : `暂停 ${c.front}`}
                onClick={() =>
                  update.mutate({
                    id: c.id,
                    body: { status: c.status === 'suspended' ? 'active' : 'suspended' },
                  })
                }
              >
                {c.status === 'suspended' ? <Play size={13} /> : <Pause size={13} />}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                aria-label={`编辑 ${c.front}`}
                onClick={() => {
                  setEditing(c)
                  setFront(c.front)
                  setBack(c.back_md)
                }}
              >
                ✎
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                aria-label={`删除 ${c.front}`}
                onClick={() => setDeleting(c)}
              >
                <Trash2 size={13} />
              </Button>
            </CardContent>
          </Card>
        ))}
        {cards?.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            还没有卡片——测验答错、对话中标记卡壳都会自动生成。
          </p>
        )}
      </div>

      {/* 编辑:只改卡片本身,历史复习记录不动(M4-04) */}
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑卡片(历史复习记录不受影响)</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (editing) update.mutate({ id: editing.id, body: { front, back_md: back } })
            }}
          >
            <Input value={front} onChange={(e) => setFront(e.target.value)} required />
            <Textarea value={back} onChange={(e) => setBack(e.target.value)} rows={4} />
            <Button type="submit" disabled={update.isPending || !front.trim()}>
              保存
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除这张卡片?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            「{deleting?.front}」将被删除,其历史复习记录一并清理,不可恢复。
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleting && remove.mutate(deleting.id)}
              disabled={remove.isPending}
            >
              确认删除
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <p className="text-xs text-muted-foreground">
        提示:测验错题与对话卡壳会自动生成卡片;复习在{' '}
        <Link to="/review" className="underline">
          复习页
        </Link>{' '}
        进行。
      </p>
    </div>
  )
}

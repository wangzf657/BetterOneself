import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { api, type Schemas } from '@/lib/api'

/** 项目列表(M1-01):卡片、新建、归档、删除(确认) */
export function StudiesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [goal, setGoal] = useState('')
  const [deleting, setDeleting] = useState<Schemas['StudyOut'] | null>(null)

  const { data: studies } = useQuery({
    queryKey: ['studies', 'all'],
    queryFn: () => api<Schemas['StudyOut'][]>('/api/studies?include_archived=true'),
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['studies'] })
  }

  const create = useMutation({
    mutationFn: () =>
      api<Schemas['StudyOut']>('/api/studies', {
        method: 'POST',
        body: JSON.stringify({ name, goal }),
      }),
    onSuccess: (s) => {
      invalidate()
      setOpen(false)
      setName('')
      setGoal('')
      navigate(`/studies/${s.id}/sources`)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const archive = useMutation({
    mutationFn: (id: number) =>
      api<void>(`/api/studies/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'archived' }),
      }),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/api/studies/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      setDeleting(null)
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const active = (studies ?? []).filter((s) => s.status === 'active')
  const archived = (studies ?? []).filter((s) => s.status === 'archived')

  return (
    <main className="mx-auto max-w-4xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">学习项目</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>新建项目</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>新建学习项目</DialogTitle>
            </DialogHeader>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                create.mutate()
              }}
            >
              <Input
                placeholder="名称,如:学 Rust"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
              <Textarea
                placeholder="一句话目标,如:读完 RustBook 并能写 CLI 工具"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                required
              />
              <Button type="submit" disabled={create.isPending || !name || !goal}>
                {create.isPending ? '创建中…' : '创建'}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {active.map((s) => (
          <Card key={s.id}>
            <CardHeader>
              <CardTitle className="text-base">
                <Link to={`/studies/${s.id}/sources`} className="hover:underline">
                  {s.name}
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-muted-foreground">{s.goal}</p>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => archive.mutate(s.id)}>
                  归档
                </Button>
                <Button size="sm" variant="destructive" onClick={() => setDeleting(s)}>
                  删除
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
        {active.length === 0 && (
          <p className="text-sm text-muted-foreground">还没有项目,点右上角新建。</p>
        )}
      </div>

      {archived.length > 0 && (
        <>
          <h2 className="mt-10 mb-3 text-sm font-medium text-muted-foreground">已归档</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {archived.map((s) => (
              <Card key={s.id} className="opacity-60">
                <CardContent className="flex items-center justify-between py-4">
                  <span className="text-sm">{s.name}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      api(`/api/studies/${s.id}`, {
                        method: 'PATCH',
                        body: JSON.stringify({ status: 'active' }),
                      }).then(invalidate)
                    }
                  >
                    恢复
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除项目「{deleting?.name}」?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            该项目的资料关联、知识点、会话记录将一并删除,不可恢复。
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
    </main>
  )
}

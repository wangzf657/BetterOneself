import { Fragment, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { api, type Schemas } from '@/lib/api'
import { ProgressLine } from '@/components/progress-line'

const TYPE_LABEL: Record<string, string> = {
  pdf: 'PDF',
  md: 'MD',
  url: '网页',
  github: 'Repo',
  text: '文本',
}

function StatusBadge({ s }: { s: Schemas['SourceOut'] }) {
  const variant =
    s.parse_status === 'ready'
      ? 'default'
      : s.parse_status === 'failed'
        ? 'destructive'
        : 'secondary'
  return (
    <Badge variant={variant}>
      {s.parse_status === 'ready'
        ? '就绪'
        : s.parse_status === 'failed'
          ? '失败'
          : s.parse_status === 'processing'
            ? '解析中'
            : '等待中'}
    </Badge>
  )
}

/** 资料管理(M1-02/05/06/07):批量文件 + 粘贴文本,重命名/删除(带派生影响提示) */
export function SourcesPage() {
  const { id: studyId } = useParams()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [textOpen, setTextOpen] = useState(false)
  const [textTitle, setTextTitle] = useState('')
  const [textContent, setTextContent] = useState('')
  const [renaming, setRenaming] = useState<Schemas['SourceOut'] | null>(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [deleting, setDeleting] = useState<Schemas['SourceOut'] | null>(null)
  const [impact, setImpact] = useState<{ chunks: number; kp_refs_cleared: number } | null>(null)

  const { data: sources } = useQuery({
    queryKey: ['sources', studyId],
    queryFn: () => api<Schemas['SourceOut'][]>(`/api/studies/${studyId}/sources`),
    refetchInterval: (q) =>
      q.state.data?.some((s) => s.parse_status === 'pending' || s.parse_status === 'processing')
        ? 2000
        : false,
  })

  // 解析/向量化实时进度(M1-06):有后台任务时每 2s 拉一次
  const { data: progressData } = useQuery({
    queryKey: ['import-progress', studyId],
    queryFn: () =>
      api<{ items: { key: string; stage: string; current: number; total: number | null }[] }>(
        `/api/studies/${studyId}/progress`,
      ),
    refetchInterval: (q) =>
      q.state.data?.items.length ||
      sources?.some((s) => s.parse_status === 'pending' || s.parse_status === 'processing')
        ? 2000
        : false,
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['sources', studyId] })

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api<Schemas['SourceOut']>(`/api/studies/${studyId}/sources`, {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: (s) => {
      toast.success(`已上传「${s.title}」,后台解析中`)
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const onFiles = (files: FileList | null) => {
    if (!files) return
    for (const f of Array.from(files)) upload.mutate(f) // M1-02 批量:逐个上传,失败单独提示
  }

  const importText = useMutation({
    mutationFn: () =>
      api<Schemas['SourceOut']>(`/api/studies/${studyId}/sources/text`, {
        method: 'POST',
        body: JSON.stringify({ title: textTitle, content: textContent }),
      }),
    onSuccess: (s) => {
      toast.success(`「${s.title}」已导入,后台解析中`)
      setTextOpen(false)
      setTextTitle('')
      setTextContent('')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const reparse = useMutation({
    mutationFn: (sid: number) =>
      api<Schemas['SourceOut']>(`/api/sources/${sid}/reparse`, { method: 'POST' }),
    onSuccess: () => {
      toast.success('已开始重新解析,完成后自动拆解')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      api<Schemas['SourceOut']>(`/api/sources/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      }),
    onSuccess: () => {
      setRenaming(null)
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/api/sources/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('资料已删除')
      setDeleting(null)
      invalidate()
      void queryClient.invalidateQueries({ queryKey: ['knowledge', studyId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const askDelete = async (s: Schemas['SourceOut']) => {
    setDeleting(s)
    try {
      setImpact(
        await api<{ chunks: number; kp_refs_cleared: number }>(`/api/sources/${s.id}/impact`),
      )
    } catch {
      setImpact(null)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div
        className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors ${dragging ? 'border-primary bg-accent/40' : 'border-border'}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          onFiles(e.dataTransfer.files)
        }}
      >
        <p className="text-sm text-muted-foreground">拖拽 PDF / Markdown(可多选)到这里,或</p>
        <div className="mt-3 flex items-center justify-center gap-2">
          <Button variant="outline" onClick={() => fileInput.current?.click()}>
            选择文件
          </Button>
          <Button variant="ghost" onClick={() => setTextOpen(true)}>
            <Plus size={14} /> 粘贴文本
          </Button>
        </div>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.md,.markdown"
          multiple
          className="hidden"
          onChange={(e) => {
            onFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      <div className="space-y-3">
        {(sources ?? []).map((s) => (
          <Fragment key={s.id}>
          <Card>
            <CardContent className="flex items-center gap-3 py-4">
              <Badge variant="outline">{TYPE_LABEL[s.type] ?? s.type}</Badge>
              <Link
                to={`${s.id}`}
                className="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
              >
                {s.title}
              </Link>
              <StatusBadge s={s} />
              <span className="hidden gap-0.5 group-hover:flex md:flex">
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`重命名 ${s.title}`}
                  onClick={() => {
                    setRenaming(s)
                    setRenameTitle(s.title)
                  }}
                >
                  <Pencil size={13} />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`删除 ${s.title}`}
                  onClick={() => void askDelete(s)}
                >
                  <Trash2 size={13} />
                </Button>
              </span>
              {(s.parse_status === 'ready' || s.parse_status === 'failed') && (
                <Button size="sm" variant="outline" onClick={() => reparse.mutate(s.id)}>
                  {s.parse_status === 'failed' ? '重试' : '重新解析'}
                </Button>
              )}
            </CardContent>
            {s.parse_status === 'failed' && s.parse_error && (
              <CardContent className="pt-0 text-xs text-destructive">{s.parse_error}</CardContent>
            )}
          </Card>
          {(s.parse_status === 'pending' || s.parse_status === 'processing') &&
            progressData?.items
              .filter((p) => p.key === `parse:${s.id}`)
              .map((p) => (
                <CardContent key={p.key} className="pt-0">
                  <ProgressLine stage={p.stage} current={p.current} total={p.total} />
                </CardContent>
              ))}
          </Fragment>
        ))}
        {sources?.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            还没有资料。导入后自动拆解知识点。
          </p>
        )}
      </div>

      {/* 粘贴文本(M1-07) */}
      <Dialog open={textOpen} onOpenChange={setTextOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>粘贴文本导入</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              importText.mutate()
            }}
          >
            <Input
              placeholder="标题"
              value={textTitle}
              onChange={(e) => setTextTitle(e.target.value)}
              required
            />
            <Textarea
              placeholder="粘贴笔记/邮件片段…(支持 Markdown 标题,便于拆解)"
              value={textContent}
              onChange={(e) => setTextContent(e.target.value)}
              rows={8}
              required
            />
            <Button type="submit" disabled={importText.isPending || !textTitle || !textContent}>
              {importText.isPending ? '导入中…' : '导入'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* 重命名(M1-05) */}
      <Dialog open={!!renaming} onOpenChange={(o) => !o && setRenaming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名资料</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (renaming) rename.mutate({ id: renaming.id, title: renameTitle })
            }}
          >
            <Input value={renameTitle} onChange={(e) => setRenameTitle(e.target.value)} required />
            <Button type="submit" disabled={!renameTitle.trim() || rename.isPending}>
              保存
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* 删除确认:展示派生影响(M1-05) */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除资料「{deleting?.title}」?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            将删除 {impact?.chunks ?? '?'} 个切片,清空 {impact?.kp_refs_cleared ?? '?'}{' '}
            处知识点来源引用 (失去引用的知识点将标注「AI 推断」,不会被静默删除)。
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
    </div>
  )
}

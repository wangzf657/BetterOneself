import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { api, type Schemas } from '@/lib/api'

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

/** 资料管理(M1-02/06):上传 → 列表轮询解析状态;URL/repo/文本入口里程碑 5 */
export function SourcesPage() {
  const { id: studyId } = useParams()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const { data: sources } = useQuery({
    queryKey: ['sources', studyId],
    queryFn: () => api<Schemas['SourceOut'][]>(`/api/studies/${studyId}/sources`),
    // 解析中/等待中每 2s 轮询;全部就绪后停(页面清单 §4 后台任务约定)
    refetchInterval: (q) =>
      q.state.data?.some((s) => s.parse_status === 'pending' || s.parse_status === 'processing')
        ? 2000
        : false,
  })

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
      void queryClient.invalidateQueries({ queryKey: ['sources', studyId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const reparse = useMutation({
    mutationFn: (sid: number) =>
      api<Schemas['SourceOut']>(`/api/sources/${sid}/reparse`, { method: 'POST' }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['sources', studyId] }),
  })

  const onFiles = (files: FileList | null) => {
    if (!files) return
    for (const f of Array.from(files)) upload.mutate(f)
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
        <p className="text-sm text-muted-foreground">拖拽 PDF / Markdown 到这里,或</p>
        <Button variant="outline" className="mt-3" onClick={() => fileInput.current?.click()}>
          选择文件
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.md,.markdown"
          className="hidden"
          onChange={(e) => {
            onFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      <div className="space-y-3">
        {(sources ?? []).map((s) => (
          <Card key={s.id}>
            <CardContent className="flex items-center gap-3 py-4">
              <Badge variant="outline">{TYPE_LABEL[s.type] ?? s.type}</Badge>
              <Link
                to={`${s.id}`}
                className="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
              >
                {s.title}
              </Link>
              <StatusBadge s={s} />
              {s.parse_status === 'failed' && (
                <Button size="sm" variant="outline" onClick={() => reparse.mutate(s.id)}>
                  重试
                </Button>
              )}
            </CardContent>
            {s.parse_status === 'failed' && s.parse_error && (
              <CardContent className="pt-0 text-xs text-destructive">{s.parse_error}</CardContent>
            )}
          </Card>
        ))}
        {sources?.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            还没有资料。导入后自动拆解知识点。
          </p>
        )}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type Schemas } from '@/lib/api'

type KpNode = Schemas['KpNode']

/** 知识点页(M2-01):树视图 + AI 推断徽标 + 引用回跳 + 开始学习;依赖图视图 M2-02(M3) */
export function KnowledgePage() {
  const { id: studyId } = useParams()
  const navigate = useNavigate()

  const { data: tree, isLoading } = useQuery({
    queryKey: ['knowledge', studyId],
    queryFn: () => api<KpNode[]>(`/api/studies/${studyId}/knowledge`),
  })

  const startSession = useMutation({
    mutationFn: (kpId: number) =>
      api<Schemas['SessionOut']>(`/api/studies/${studyId}/sessions`, {
        method: 'POST',
        body: JSON.stringify({ kp_id: kpId }),
      }),
    onSuccess: (s) => navigate(`/studies/${studyId}/learn/${s.id}`),
  })

  if (isLoading) return <Skeleton className="h-96 w-full" />

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-6 text-2xl font-semibold">知识点</h1>
      {tree?.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          还没有知识点。先到
          <Link to={`/studies/${studyId}/sources`} className="mx-1 underline">
            资料
          </Link>
          页导入内容,导入完成后会自动拆解。
        </div>
      )}
      <div className="space-y-1">
        {(tree ?? []).map((n) => (
          <KpRow key={n.id} node={n} depth={0} studyId={studyId!} onStart={startSession.mutate} />
        ))}
      </div>
    </div>
  )
}

function KpRow({
  node,
  depth,
  studyId,
  onStart,
}: {
  node: KpNode
  depth: number
  studyId: string
  onStart: (id: number) => void
}) {
  const [open, setOpen] = useState(true)
  const hasChildren = node.children.length > 0

  return (
    <div>
      <div
        className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent/40"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
      >
        <button
          type="button"
          className="text-muted-foreground"
          onClick={() => setOpen(!open)}
          aria-label={open ? '折叠' : '展开'}
        >
          {hasChildren ? (
            open ? (
              <ChevronDown size={16} />
            ) : (
              <ChevronRight size={16} />
            )
          ) : (
            <span className="inline-block w-4" />
          )}
        </button>
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{node.name}</span>
        {node.ai_inferred && (
          <Badge variant="outline" className="text-[10px]">
            AI 推断
          </Badge>
        )}
        {node.refs.length > 0 && (
          <Link
            to={`/studies/${studyId}/sources/${node.refs[0].source_id}?chunk=${node.refs[0].chunk_id}`}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            来源({node.refs.length})
          </Link>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="opacity-0 transition-opacity group-hover:opacity-100"
          onClick={() => onStart(node.id)}
        >
          开始学习
        </Button>
      </div>
      {open &&
        node.children.map((c) => (
          <KpRow key={c.id} node={c} depth={depth + 1} studyId={studyId} onStart={onStart} />
        ))}
      {open && node.summary && !hasChildren && (
        <p
          className="py-1 text-xs text-muted-foreground"
          style={{ paddingLeft: `${depth * 20 + 36}px` }}
        >
          {node.summary}
        </p>
      )}
    </div>
  )
}

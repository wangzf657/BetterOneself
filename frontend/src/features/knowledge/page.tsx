import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronDown,
  ChevronRight,
  Pencil,
  Plus,
  Trash2,
  GitBranch,
  ListTree,
  Merge,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  type Edge,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { api, type Schemas } from '@/lib/api'

type KpNode = Schemas['KpNode']

/** 知识点页(M2-01/02/03):树⇄依赖图切换、编辑(增删改/合并)、AI 推断徽标、引用回跳、开始学习 */
export function KnowledgePage() {
  const { id: studyId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [view, setView] = useState<'tree' | 'graph'>('tree')
  const [editing, setEditing] = useState<KpNode | null>(null)
  const [creating, setCreating] = useState<{ parentId: number | null } | null>(null)
  const [merging, setMerging] = useState<KpNode | null>(null)

  const { data: tree, isLoading } = useQuery({
    queryKey: ['knowledge', studyId],
    queryFn: () => api<KpNode[]>(`/api/studies/${studyId}/knowledge`),
  })
  const { data: graph } = useQuery({
    queryKey: ['kp-graph', studyId],
    queryFn: () =>
      api<{
        nodes: { id: number; name: string; mastery_status: string; ai_inferred: boolean }[]
        edges: { source: number; depends_on: number }[]
      }>(`/api/studies/${studyId}/kp-graph`),
    enabled: view === 'graph',
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['knowledge', studyId] })
    void queryClient.invalidateQueries({ queryKey: ['kp-graph', studyId] })
  }

  const startSession = useMutation({
    mutationFn: (kpId: number) =>
      api<Schemas['SessionOut']>(`/api/studies/${studyId}/sessions`, {
        method: 'POST',
        body: JSON.stringify({ kp_id: kpId }),
      }),
    onSuccess: (s) => navigate(`/studies/${studyId}/learn/${s.id}`),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/api/kps/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('已删除(关联卡片/任务一并移除)')
      invalidate()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const flat = useMemo(() => {
    const out: KpNode[] = []
    const walk = (nodes: KpNode[]) => {
      for (const n of nodes) {
        out.push(n)
        walk(n.children)
      }
    }
    walk(tree ?? [])
    return out
  }, [tree])

  if (isLoading) return <Skeleton className="h-96 w-full" />

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-center gap-2">
        <h1 className="text-2xl font-semibold">知识点</h1>
        <div className="ml-auto flex rounded-md border p-0.5 text-sm">
          <button
            type="button"
            className={`flex items-center gap-1 rounded px-2 py-1 ${view === 'tree' ? 'bg-accent font-medium' : 'text-muted-foreground'}`}
            onClick={() => setView('tree')}
          >
            <ListTree size={14} /> 树
          </button>
          <button
            type="button"
            className={`flex items-center gap-1 rounded px-2 py-1 ${view === 'graph' ? 'bg-accent font-medium' : 'text-muted-foreground'}`}
            onClick={() => setView('graph')}
          >
            <GitBranch size={14} /> 依赖图
          </button>
        </div>
        <Button size="sm" variant="outline" onClick={() => setCreating({ parentId: null })}>
          <Plus size={14} /> 新增
        </Button>
      </div>

      {tree?.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          还没有知识点。先到
          <Link to={`/studies/${studyId}/sources`} className="mx-1 underline">
            资料
          </Link>
          页导入内容,导入完成后会自动拆解。
        </div>
      )}

      {view === 'tree' ? (
        <div className="space-y-1" data-testid="kp-tree">
          {(tree ?? []).map((n) => (
            <KpRow
              key={n.id}
              node={n}
              depth={0}
              onStart={startSession.mutate}
              onEdit={setEditing}
              onDelete={(node) => {
                if (window.confirm(`删除「${node.name}」?其关联卡片、测验与任务将一并删除。`))
                  remove.mutate(node.id)
              }}
              onMerge={setMerging}
              onCreateChild={(parentId) => setCreating({ parentId })}
            />
          ))}
        </div>
      ) : (
        <div className="h-[560px] rounded-lg border" data-testid="kp-graph">
          {graph && <DepGraph nodes={graph.nodes} edges={graph.edges} />}
        </div>
      )}

      {/* 编辑对话框:key 重挂载以按所选 kp 重置表单 */}
      {editing && (
        <KpEditDialog
          key={editing.id}
          kp={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            invalidate()
          }}
        />
      )}
      {/* 新增对话框 */}
      <KpCreateDialog
        studyId={Number(studyId)}
        parentId={creating?.parentId ?? null}
        open={creating !== null}
        onClose={() => setCreating(null)}
        onSaved={() => {
          setCreating(null)
          invalidate()
        }}
      />
      {/* 合并对话框 */}
      {merging && (
        <KpMergeDialog
          key={merging.id}
          source={merging}
          exclude={flat}
          onClose={() => setMerging(null)}
          onSaved={() => {
            setMerging(null)
            invalidate()
          }}
        />
      )}
    </div>
  )
}

function KpRow({
  node,
  depth,
  onStart,
  onEdit,
  onDelete,
  onMerge,
  onCreateChild,
}: {
  node: KpNode
  depth: number
  onStart: (id: number) => void
  onEdit: (n: KpNode) => void
  onDelete: (n: KpNode) => void
  onMerge: (n: KpNode) => void
  onCreateChild: (parentId: number) => void
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
        {node.mastery_status === 'weak' && (
          <Badge variant="destructive" className="text-[10px]">
            薄弱
          </Badge>
        )}
        {node.mastery_status === 'passed' && (
          <Badge variant="default" className="text-[10px]">
            已通过
          </Badge>
        )}
        {node.ai_inferred && (
          <Badge variant="outline" className="text-[10px]">
            AI 推断
          </Badge>
        )}
        {node.refs.length > 0 && (
          <Link
            to={`/studies/0/sources/${node.refs[0].source_id}?chunk=${node.refs[0].chunk_id}`}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            来源({node.refs.length})
          </Link>
        )}
        <span className="hidden gap-0.5 group-hover:flex">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label={`编辑 ${node.name}`}
            onClick={() => onEdit(node)}
          >
            <Pencil size={13} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label={`在 ${node.name} 下新增`}
            onClick={() => onCreateChild(node.id)}
          >
            <Plus size={13} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label={`合并 ${node.name}`}
            onClick={() => onMerge(node)}
          >
            <Merge size={13} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            aria-label={`删除 ${node.name}`}
            onClick={() => onDelete(node)}
          >
            <Trash2 size={13} />
          </Button>
        </span>
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
          <KpRow
            key={c.id}
            node={c}
            depth={depth + 1}
            onStart={onStart}
            onEdit={onEdit}
            onDelete={onDelete}
            onMerge={onMerge}
            onCreateChild={onCreateChild}
          />
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

function KpEditDialog({
  kp,
  onClose,
  onSaved,
}: {
  kp: KpNode
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(kp.name)
  const [summary, setSummary] = useState(kp.summary)
  const save = useMutation({
    mutationFn: () =>
      api(`/api/kps/${kp.id}`, { method: 'PATCH', body: JSON.stringify({ name, summary }) }),
    onSuccess: onSaved,
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑知识点</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <Input value={name} onChange={(e) => setName(e.target.value)} required />
          <Textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={3}
            placeholder="简介"
          />
          <Button type="submit" disabled={save.isPending || !name.trim()}>
            保存
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function KpCreateDialog({
  studyId,
  parentId,
  open,
  onClose,
  onSaved,
}: {
  studyId: number
  parentId: number | null
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState('')
  const [summary, setSummary] = useState('')
  const save = useMutation({
    mutationFn: () =>
      api(`/api/studies/${studyId}/kps`, {
        method: 'POST',
        body: JSON.stringify({ name, summary, parent_id: parentId }),
      }),
    onSuccess: () => {
      setName('')
      setSummary('')
      onSaved()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setName('')
          setSummary('')
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{parentId ? '新增子知识点' : '新增知识点'}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="名称"
            required
          />
          <Textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={3}
            placeholder="简介(可选)"
          />
          <Button type="submit" disabled={save.isPending || !name.trim()}>
            创建
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function KpMergeDialog({
  source,
  exclude,
  onClose,
  onSaved,
}: {
  source: KpNode
  exclude: KpNode[]
  onClose: () => void
  onSaved: () => void
}) {
  const [targetId, setTargetId] = useState('')
  const candidates = exclude.filter((n) => n.id !== source.id)
  const merge = useMutation({
    mutationFn: () =>
      api(`/api/kps/${source.id}/merge`, {
        method: 'POST',
        body: JSON.stringify({ target_id: Number(targetId) }),
      }),
    onSuccess: () => {
      toast.success('已合并')
      onSaved()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>把「{source.name}」合并到…</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <select
            className="h-9 w-full rounded-md border bg-transparent px-2 text-sm"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
          >
            <option value="">选择目标知识点…</option>
            {candidates.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </select>
          <p className="text-xs text-muted-foreground">
            来源引用、子节点、卡片与任务都会转移到目标,原知识点删除。
          </p>
          <Button disabled={!targetId || merge.isPending} onClick={() => merge.mutate()}>
            合并
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** 依赖图(M2-02):@xyflow/react 分层布局,边=depends_on → kp */
function DepGraph({
  nodes,
  edges,
}: {
  nodes: { id: number; name: string; mastery_status: string; ai_inferred: boolean }[]
  edges: { source: number; depends_on: number }[]
}) {
  const flowNodes: Node[] = useMemo(() => {
    const indeg = new Map<number, number>()
    nodes.forEach((n) => indeg.set(n.id, 0))
    edges.forEach((e) => indeg.set(e.source, (indeg.get(e.source) ?? 0) + 1))
    const level = new Map<number, number>()
    let frontier = nodes.filter((n) => (indeg.get(n.id) ?? 0) === 0).map((n) => n.id)
    frontier.forEach((id) => level.set(id, 0))
    while (frontier.length) {
      const next: number[] = []
      for (const id of frontier) {
        for (const e of edges.filter((x) => x.depends_on === id)) {
          const lv = (level.get(id) ?? 0) + 1
          if ((level.get(e.source) ?? -1) < lv) {
            level.set(e.source, lv)
            next.push(e.source)
          }
        }
      }
      frontier = next
    }
    const byLevel = new Map<number, number[]>()
    for (const n of nodes) {
      const lv = level.get(n.id) ?? 0
      byLevel.set(lv, [...(byLevel.get(lv) ?? []), n.id])
    }
    const out: Node[] = []
    for (const [lv, ids] of byLevel) {
      ids.forEach((id, i) => {
        const meta = nodes.find((n) => n.id === id)!
        out.push({
          id: String(id),
          position: { x: i * 190, y: lv * 110 },
          data: { label: `${meta.name}${meta.ai_inferred ? ' (AI)' : ''}` },
          style: { fontSize: 12, padding: 6 },
        })
      })
    }
    return out
  }, [nodes, edges])

  const flowEdges: Edge[] = useMemo(
    () =>
      edges.map((e, i) => ({
        id: `e${i}`,
        source: String(e.depends_on),
        target: String(e.source),
        animated: true,
      })),
    [edges],
  )

  return (
    <ReactFlowProvider>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </ReactFlowProvider>
  )
}

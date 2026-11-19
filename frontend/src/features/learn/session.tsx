import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkPlus, BookOpen, ChevronDown, ChevronRight, PanelRightClose, PanelRightOpen } from 'lucide-react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { RichMessage } from '@/components/citation'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { QuizPanel, SaveCardForm } from '@/features/learn/quiz-panel'
import { api, streamChat, type Schemas } from '@/lib/api'

type Citation = Schemas['Citation']

/** 学习会话页(页面清单 #8/§3):任务头+对话流(含测验)+源文侧栏;输入框 SSE 流式讲解 */
export function LearnPage() {
  const { sessionId } = useParams()
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [live, setLive] = useState<string | null>(null) // 流式中的回答
  const [sidebarCite, setSidebarCite] = useState<Citation | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const { data: session } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api<Schemas['SessionDetail']>(`/api/sessions/${sessionId}`),
  })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [session?.messages.length, live])

  const toggleSocratic = useMutation({
    mutationFn: (on: boolean) =>
      api<Schemas['SessionOut']>(`/api/sessions/${sessionId}/socratic`, {
        method: 'PATCH',
        body: JSON.stringify({ socratic_mode: on }),
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['session', sessionId] }),
  })

  async function send() {
    const content = input.trim()
    if (!content || live !== null) return
    setInput('')
    setLive('')
    try {
      await streamChat(Number(sessionId), content, {
        onDelta: (t) => setLive((prev) => (prev ?? '') + t),
        onDone: () => setLive(null),
      })
      await queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
    } catch (err) {
      setLive(null)
      throw err
    } finally {
      setLive(null)
    }
  }

  if (!session) return <Skeleton className="h-96 w-full" />

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* 任务头 */}
      <div className="flex items-center gap-3 border-b px-6 py-2.5">
        <h1 className="text-sm font-semibold">
          学习会话 · {session.session_type === 'lecture' ? '讲解' : session.session_type}
        </h1>
        <div className="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
          <span>苏格拉底引导</span>
          <Switch
            checked={session.socratic_mode}
            onCheckedChange={(on) => toggleSocratic.mutate(on)}
            aria-label="切换苏格拉底模式"
          />
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() =>
            setSidebarCite((c) =>
              c
                ? null
                : (session.messages.findLast((m) => m.citations.length > 0)?.citations[0] ?? null),
            )
          }
          aria-label="源文侧栏"
        >
          {sidebarCite ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* 对话流 */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* 自由提问切换线程(M3-06):同资料不限当日知识点,不改变计划 */}
          {session.session_type !== 'free' && (
            <div className="border-b px-6 py-1.5 text-xs">
              <FreeQuestionLink studyId={session.study_id} />
            </div>
          )}
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            <div className="mx-auto max-w-2xl space-y-4">
              {/* 原文预习(V1.1 B7-02 简易版):先见原文与摘要,再提问 */}
              {session.kp_id != null && (
                <KpPreview studyId={session.study_id} kpId={session.kp_id} />
              )}
              {session.messages.map((m) => (
                <div
                  key={m.id}
                  className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
                >
                  {m.role === 'user' ? (
                    <div className="max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                      {m.content}
                    </div>
                  ) : (
                    <div className="max-w-full rounded-lg border bg-card px-4 py-3">
                      <RichMessage
                        content={m.content}
                        citations={m.citations}
                        onOpen={setSidebarCite}
                      />
                    </div>
                  )}
                </div>
              ))}
              {live !== null && (
                <div className="flex justify-start">
                  <div className="max-w-full rounded-lg border bg-card px-4 py-3">
                    <RichMessage content={live || '…'} citations={[]} onOpen={setSidebarCite} />
                  </div>
                </div>
              )}
              {session.messages.length === 0 && live === null && (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  先看上方原文与摘要,不懂的直接问;准备好了点下方「考我一组」。
                </div>
              )}
              {/* 内嵌测验(M3-04) */}
              <QuizPanel sessionId={session.id} studyId={session.study_id} />
            </div>
          </div>

          {/* 输入区 */}
          <div className="border-t px-6 py-3">
            <div className="mx-auto flex max-w-2xl items-end gap-2">
              <Button
                variant="outline"
                size="icon"
                aria-label="存为卡片"
                title="把这段讲解存为复习卡片"
                onClick={() => setSaveOpen(true)}
              >
                <BookmarkPlus size={16} />
              </Button>
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send()
                  }
                }}
                placeholder="就当前知识点提问…(Enter 发送,Shift+Enter 换行)"
                rows={2}
                disabled={live !== null}
              />
              <Button onClick={() => void send()} disabled={live !== null || !input.trim()}>
                {live !== null ? '回答中…' : '发送'}
              </Button>
            </div>
          </div>
        </div>

        {/* 源文侧栏 */}
        {sidebarCite && <SourceSidebar cite={sidebarCite} />}
      </div>

      {/* 存为卡片(M3-05 手动沉淀);key 重挂载以重置预填 */}
      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>存为复习卡片</DialogTitle>
          </DialogHeader>
          {saveOpen && (
            <SaveCardForm
              key={`save-${session.id}-${session.messages.length}`}
              onDone={() => setSaveOpen(false)}
              studyId={session.study_id}
              kpId={session.kp_id}
              prefill={session.messages.findLast((m) => m.role === 'assistant')?.content ?? ''}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** 原文预习面板(V1.1 B7-02 简易版):知识点的摘要与原文切片,先读后问 */
function KpPreview({ studyId, kpId }: { studyId: number; kpId: number }) {
  const [open, setOpen] = useState(true)
  type Node = {
    id: number
    name: string
    summary: string
    refs: { chunk_id: number; source_id: number; heading_path: string }[]
    children: Node[]
  }
  const { data: tree } = useQuery({
    queryKey: ['knowledge', String(studyId)],
    queryFn: () => api<Node[]>(`/api/studies/${studyId}/knowledge`),
  })
  const node = useMemo(() => {
    const walk = (nodes: Node[]): Node | null => {
      for (const n of nodes) {
        if (n.id === kpId) return n
        const hit = walk(n.children)
        if (hit) return hit
      }
      return null
    }
    return tree ? walk(tree) : null
  }, [tree, kpId])

  const refs = useMemo(() => node?.refs ?? [], [node])
  const sourceIds = useMemo(() => [...new Set(refs.map((r) => r.source_id))], [refs])
  // shortcut: 复用整包源文接口,大资料拉取偏重;V1.1 B7-02 上轻量内容端点后替换
  const sourceQueries = useQueries({
    queries: sourceIds.map((sid) => ({
      queryKey: ['source', sid],
      queryFn: () => api<Schemas['SourceDetail']>(`/api/sources/${sid}`),
    })),
  })
  const chunkById = new Map<number, Schemas['ChunkOut']>()
  for (const q of sourceQueries) {
    for (const c of q.data?.chunks ?? []) chunkById.set(c.id, c)
  }

  if (!node) return null
  return (
    <div className="rounded-lg border bg-muted/30" data-testid="kp-preview">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium"
        onClick={() => setOpen(!open)}
        aria-label="展开原文预习"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <BookOpen size={14} />
        原文预习 · {node.name}
      </button>
      {open && (
        <div className="space-y-3 px-4 pb-3">
          {node.summary && <p className="text-sm text-muted-foreground">{node.summary}</p>}
          {refs.length === 0 && (
            <p className="text-xs text-muted-foreground">该知识点暂无原文切片(AI 推断)。</p>
          )}
          {refs.map((r) => {
            const chunk = chunkById.get(r.chunk_id)
            return (
              <section key={r.chunk_id} className="rounded-md border bg-card p-2">
                <div className="mb-1 text-xs text-muted-foreground">
                  {r.heading_path || `chunk ${r.chunk_id}`}
                </div>
                <div className="prose prose-xs dark:prose-invert max-w-none text-sm">
                  {chunk ? (
                    <Markdown remarkPlugins={[remarkGfm]}>{chunk.content}</Markdown>
                  ) : (
                    <Skeleton className="h-16 w-full" />
                  )}
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** 源文侧栏:显示被引用 chunk 所在资料片段并高亮定位(页面清单 §3 引用角标交互) */
function SourceSidebar({ cite }: { cite: Citation }) {
  const { data: source } = useQuery({
    queryKey: ['source', cite.source_id],
    queryFn: () => api<Schemas['SourceDetail']>(`/api/sources/${cite.source_id}`),
  })

  return (
    <aside className="w-96 shrink-0 border-l">
      <div className="border-b px-4 py-2 text-xs text-muted-foreground">
        源文:{cite.heading_path || `chunk ${cite.chunk_id}`}
      </div>
      <ScrollArea className="h-[calc(100%-2.25rem)]">
        <div className="p-3">
          {!source && <Skeleton className="h-40 w-full" />}
          {source?.chunks.map((c) => (
            <section
              key={c.id}
              className={`mb-3 rounded-md p-2 text-sm ${c.id === cite.chunk_id ? 'bg-accent/60 ring-1 ring-primary/40' : 'opacity-60'}`}
            >
              <div className="prose prose-xs dark:prose-invert max-w-none">
                <Markdown remarkPlugins={[remarkGfm]}>{c.content}</Markdown>
              </div>
            </section>
          ))}
        </div>
      </ScrollArea>
    </aside>
  )
}

/** 自由提问入口(M3-06):创建 free 会话切换线程;回答带引用,不改变当日计划 */
function FreeQuestionLink({ studyId }: { studyId: number }) {
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)
  return (
    <button
      type="button"
      className="text-muted-foreground underline-offset-2 hover:underline disabled:opacity-50"
      disabled={pending}
      onClick={() => {
        setPending(true)
        api<Schemas['SessionOut']>(`/api/studies/${studyId}/sessions`, {
          method: 'POST',
          body: JSON.stringify({ session_type: 'free' }),
        })
          .then((s) => navigate(`/studies/${studyId}/learn/${s.id}`))
          .catch(() => setPending(false))
      }}
    >
      自由提问:不限本知识点,就当前资料随便问 →(新线程)
    </button>
  )
}

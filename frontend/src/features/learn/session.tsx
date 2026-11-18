import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { RichMessage } from '@/components/citation'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { api, streamChat, type Schemas } from '@/lib/api'

type Citation = Schemas['Citation']

/** 学习会话页(页面清单 #8/§3):任务头+对话流+源文侧栏;输入框发送 SSE 流式讲解 */
export function LearnPage() {
  const { sessionId } = useParams()
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [live, setLive] = useState<string | null>(null) // 流式中的回答
  const [sidebarCite, setSidebarCite] = useState<Citation | null>(null)
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
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            <div className="mx-auto max-w-2xl space-y-4">
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
                <div className="py-16 text-center text-sm text-muted-foreground">
                  提个问题开始学习——讲解默认引导式,回答会带来源引用。
                </div>
              )}
            </div>
          </div>

          {/* 输入区 */}
          <div className="border-t px-6 py-3">
            <div className="mx-auto flex max-w-2xl items-end gap-2">
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

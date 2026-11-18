import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type Schemas } from '@/lib/api'

/** 资料阅读页(页面清单 #4):左目录树,右正文;?chunk= 定位高亮(全站引用回跳目标) */
export function SourceReadPage() {
  const { sid } = useParams()
  const [params] = useSearchParams()
  const highlight = Number(params.get('chunk') ?? 0)

  const { data: source } = useQuery({
    queryKey: ['source', sid],
    queryFn: () => api<Schemas['SourceDetail']>(`/api/sources/${sid}`),
    refetchInterval: (q) =>
      q.state.data && ['pending', 'processing'].includes(q.state.data.parse_status) ? 2000 : false,
  })

  const toc = useMemo(() => buildToc(source?.chunks ?? []), [source])

  if (!source) return <Skeleton className="h-96 w-full" />
  if (source.parse_status !== 'ready') {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        {source.parse_status === 'failed'
          ? `解析失败:${source.parse_error ?? '未知原因'}`
          : '解析中…请稍后。'}
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] gap-6 pr-6">
      <ScrollArea className="w-60 shrink-0 border-l pl-2">
        <nav className="py-4 text-sm">
          {toc.map((n) => (
            <a
              key={n.key}
              href={`#chunk-${n.chunkId}`}
              className={`block truncate rounded px-2 py-1 text-muted-foreground hover:bg-accent/50 ${n.depth === 0 ? 'font-medium text-foreground' : ''}`}
              style={{ paddingLeft: `${n.depth * 12 + 8}px` }}
            >
              {n.label}
            </a>
          ))}
        </nav>
      </ScrollArea>
      <ScrollArea className="min-w-0 flex-1">
        <article className="max-w-3xl py-4">
          <h1 className="mb-6 text-xl font-semibold">{source.title}</h1>
          {source.chunks.map((c) => (
            <section
              key={c.id}
              id={`chunk-${c.id}`}
              className={`mb-4 scroll-mt-4 rounded-md p-2 transition-colors ${highlight === c.id ? 'bg-accent/60 ring-1 ring-primary/40' : ''}`}
            >
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <Markdown remarkPlugins={[remarkGfm]}>{c.content}</Markdown>
              </div>
            </section>
          ))}
        </article>
      </ScrollArea>
    </div>
  )
}

interface TocNode {
  key: string
  label: string
  depth: number
  chunkId: number
}

/** heading_path 形如 `章 > 节`,按层级展开成可点目录 */
function buildToc(chunks: Schemas['ChunkOut'][]): TocNode[] {
  const nodes: TocNode[] = []
  const seen = new Set<string>()
  for (const c of chunks) {
    const parts = c.heading_path.split(' > ').filter(Boolean)
    parts.forEach((label, depth) => {
      const key = `${parts.slice(0, depth + 1).join('/')}`
      if (!seen.has(key)) {
        seen.add(key)
        nodes.push({ key, label, depth, chunkId: c.id })
      }
    })
  }
  return nodes
}

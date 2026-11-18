import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Schemas } from '@/lib/api'

type Citation = Schemas['Citation']

/** 引用角标(页面清单 §4 全站统一交互):悬停预览章节,点击回跳源文 */
export function CitationChip({ c, onOpen }: { c: Citation; onOpen: (c: Citation) => void }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => onOpen(c)}
          className="mx-0.5 inline-flex h-4 min-w-4 cursor-pointer items-center justify-center rounded-sm bg-accent px-1 align-super text-[10px] font-medium text-accent-foreground/80 hover:bg-accent/70"
          aria-label={`来源:${c.heading_path || `chunk ${c.chunk_id}`}`}
        >
          {c.index}
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        <div className="text-xs">{c.heading_path || `chunk ${c.chunk_id}`}</div>
      </TooltipContent>
    </Tooltip>
  )
}

/** 消息文本渲染:段末 [n] 角标化(提示词约束引用只出现在句末/段末) */
export function RichMessage({
  content,
  citations,
  onOpen,
}: {
  content: string
  citations: Citation[]
  onOpen: (c: Citation) => void
}) {
  const byIndex = new Map(citations.map((c) => [c.index, c]))
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      {content.split(/\n{2,}/).map((para, i) => {
        // 段末角标,允许其后跟句读/空白(提示词约束引用在句末)
        const m = para.match(/(?:\[\d+\])+[。.!?!!??\s]*$/)
        if (!m || m.index === undefined) return <p key={i}>{para}</p>
        const body = para.slice(0, m.index)
        const nums = [...para.slice(m.index).matchAll(/\[(\d+)\]/g)].map((x) => Number(x[1]))
        return (
          <p key={i}>
            {body}
            {nums.map((n) => {
              const cite = byIndex.get(n)
              return cite ? <CitationChip key={n} c={cite} onOpen={onOpen} /> : null
            })}
          </p>
        )
      })}
    </div>
  )
}

import { PanelLeftClose, Quote, Search } from "lucide-react";
import { useState } from "react";
import type { NodeContent } from "@/api/client";
import { cn } from "@/lib/utils";

/** 左侧原文框（B3-02）：只加载本节点 refs，选中段落浮出「就这段追问 / 记到笔记」。 */
export default function SourcePane({
  content,
  highlightChunkId,
  onCite,
  onAskAbout,
  onQuoteToNote,
  collapsed,
  onToggle,
}: {
  content?: NodeContent;
  highlightChunkId: number | null;
  onCite: (chunkId: number) => void;
  onAskAbout: (text: string) => void;
  onQuoteToNote: (text: string, chunkId: number) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  if (collapsed) {
    return (
      <button
        className="flex h-full w-10 shrink-0 flex-col items-center gap-2 border-r bg-white pt-3 text-xs text-ink-soft hover:bg-black/5"
        onClick={onToggle}
        title="展开原文"
      >
        <PanelLeftClose size={16} className="rotate-180" />
        <span className="[writing-mode:vertical-rl] tracking-widest">原文</span>
      </button>
    );
  }
  return (
    <div className="relative flex h-full w-[400px] shrink-0 flex-col border-r bg-white">
      <div className="flex h-11 shrink-0 items-center justify-between border-b px-4">
        <span className="text-sm font-medium">原文</span>
        <button className="text-ink-soft hover:text-ink" onClick={onToggle} title="收起原文">
          <PanelLeftClose size={16} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 text-sm leading-7">
        {!content && <p className="text-ink-soft">原文加载中…</p>}
        {content?.chunks.length === 0 && <p className="text-ink-soft">该节点暂无原文引用。</p>}
        {content?.chunks.map((c) => (
          <Section
            key={c.id}
            chunk={c}
            highlighted={highlightChunkId === c.id}
            onCite={onCite}
            onAskAbout={onAskAbout}
            onQuoteToNote={onQuoteToNote}
          />
        ))}
      </div>
    </div>
  );
}

function Section({
  chunk,
  highlighted,
  onCite,
  onAskAbout,
  onQuoteToNote,
}: {
  chunk: NodeContent["chunks"][number];
  highlighted: boolean;
  onCite: (chunkId: number) => void;
  onAskAbout: (text: string) => void;
  onQuoteToNote: (text: string, chunkId: number) => void;
}) {
  return (
    <section
      id={`chunk-${chunk.id}`}
      className={cn(
        "mb-4 scroll-mt-4 rounded-md p-2 transition-colors",
        highlighted && "bo-quote-highlight",
      )}
    >
      <button
        className="mb-1 block text-xs font-medium text-ink-soft hover:text-ink"
        onClick={() => onCite(chunk.id)}
        title="在陪学中引用这段"
      >
        {chunk.title} · {locText(chunk.location)}
      </button>
      <SelectableText
        onAskAbout={onAskAbout}
        onQuoteToNote={(text) => onQuoteToNote(text, chunk.id)}
      >
        {chunk.content}
      </SelectableText>
    </section>
  );
}

/** 选段浮出菜单（就这段追问 / 记到笔记）。 */
function SelectableText({
  children,
  onAskAbout,
  onQuoteToNote,
}: {
  children: string;
  onAskAbout: (text: string) => void;
  onQuoteToNote: (text: string) => void;
}) {
  const [menu, setMenu] = useState<{ x: number; y: number; text: string } | null>(null);
  return (
    <div
      className="relative whitespace-pre-wrap"
      onMouseUp={() => {
        const sel = window.getSelection();
        const text = sel?.toString().trim() ?? "";
        if (text.length >= 8) {
          const rect = sel!.getRangeAt(0).getBoundingClientRect();
          setMenu({ x: rect.left + rect.width / 2, y: rect.top - 6, text: text.slice(0, 300) });
        } else setMenu(null);
      }}
    >
      {children}
      {menu && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setMenu(null)} />
          <div
            className="fixed z-50 flex -translate-x-1/2 -translate-y-full items-center gap-1 rounded-md border bg-white p-1 shadow-lg"
            style={{ left: menu.x, top: menu.y }}
          >
            <button
              className="flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-black/5"
              onClick={() => {
                onAskAbout(menu.text);
                setMenu(null);
              }}
            >
              <Search size={13} /> 就这段追问
            </button>
            <button
              className="flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-black/5"
              onClick={() => {
                onQuoteToNote(menu.text);
                setMenu(null);
              }}
            >
              <Quote size={13} /> 记到笔记
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function locText(loc: Record<string, unknown>): string {
  if (loc.type === "pdf") return `第 ${(loc.page_start as number) + 1} 页`;
  if (loc.type === "lines") return `第 ${loc.line_start}–${loc.line_end} 行`;
  if (loc.type === "epub") return String(loc.href).split("/").pop() ?? "";
  return "位置不可用";
}

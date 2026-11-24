import { PanelLeftClose, Quote, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { NodeContent } from "@/api/client";
import { bookPref, cn } from "@/lib/utils";
import OriginalView, { toTarget } from "./OriginalView";

type SourceView = "parsed" | "original";

/** 左侧原文框（B3-02、B6-07）：解析文本/原文双视图，切换按当前阅读位置同步定位。 */
export default function SourcePane({
  studyId,
  content,
  highlightChunkId,
  onCite,
  onAskAbout,
  onQuoteToNote,
  collapsed,
  onToggle,
}: {
  studyId: number;
  content?: NodeContent;
  highlightChunkId: number | null;
  onCite: (chunkId: number) => void;
  onAskAbout: (text: string) => void;
  onQuoteToNote: (text: string, chunkId: number) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const chunks = content?.chunks ?? [];
  const [view, setView] = useState<SourceView>(() => bookPref(studyId, "srcView", "parsed"));
  const choose = (v: SourceView) => {
    setView(v);
    bookPref(studyId, "srcView", "parsed", v);
  };

  // 定位桥：引用/回跳指向的切片是「当前位置」；原文视图滚动回报它对应的切片
  const [lastCited, setLastCited] = useState<number | null>(null);
  useEffect(() => {
    if (highlightChunkId !== null) setLastCited(highlightChunkId);
  }, [highlightChunkId]);
  const [origPos, setOrigPos] = useState<number | null>(null);
  const handleLocate = useCallback((id: number | null) => setOrigPos((p) => (p === id ? p : id)), []);

  const posChunk = chunks.find((c) => c.id === (highlightChunkId ?? lastCited)) ?? chunks[0] ?? null;
  const backChunkId = origPos ?? lastCited ?? chunks[0]?.id ?? null;
  // 无原文位置（无来源/无 location 坐标）时原文按钮禁用，视图收敛回解析文本
  const hasOriginal = chunks.length > 0 && posChunk !== null && toTarget(posChunk) !== null;
  const effectiveView: SourceView = view === "original" && hasOriginal && content?.source_id != null ? "original" : "parsed";

  // 切回解析文本：滚到原文视图回报的切片（匹配不到回上次定位，B6-07 验收 2）
  const [flashId, setFlashId] = useState<number | null>(null);
  const prevView = useRef<SourceView>(view);
  useEffect(() => {
    const wasOriginal = prevView.current === "original";
    prevView.current = view;
    // 只在「原文 → 解析文本」时回跳：进入原文视图不触发
    if (!wasOriginal || view !== "parsed" || backChunkId === null) return;
    const id = backChunkId;
    const t = setTimeout(() => {
      document.getElementById(`chunk-${id}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
      setFlashId(id);
      setTimeout(() => setFlashId(null), 1600);
    }, 60);
    return () => clearTimeout(t);
  }, [view, backChunkId]);

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
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b px-3">
        <span className="text-sm font-medium">原文</span>
        <div className="flex rounded-md border bg-white p-0.5 text-xs" role="group" aria-label="原文视图切换">
          <button
            className={cn(
              "rounded px-2 py-0.5",
              effectiveView === "parsed" ? "bg-ink text-white" : "text-ink-soft hover:text-ink",
            )}
            aria-pressed={effectiveView === "parsed"}
            onClick={() => choose("parsed")}
          >
            解析文本
          </button>
          <button
            className={cn(
              "rounded px-2 py-0.5",
              effectiveView === "original" ? "bg-ink text-white" : "text-ink-soft hover:text-ink",
            )}
            aria-pressed={effectiveView === "original"}
            disabled={!hasOriginal}
            title={hasOriginal ? "查看无损原文" : "该节点没有可定位的原文"}
            onClick={() => choose("original")}
          >
            原文
          </button>
        </div>
        <button className="text-ink-soft hover:text-ink" onClick={onToggle} title="收起原文">
          <PanelLeftClose size={16} />
        </button>
      </div>
      {effectiveView === "original" && content?.source_id != null ? (
        <div className="min-h-0 flex-1">
          <OriginalView
            sourceId={content.source_id}
            sourceType={content.source_type ?? ""}
            chunks={chunks}
            target={posChunk ? toTarget(posChunk) : null}
            onLocate={handleLocate}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3 text-sm leading-7">
          {!content && <p className="text-ink-soft">原文加载中…</p>}
          {content?.chunks.length === 0 && <p className="text-ink-soft">该节点暂无原文引用。</p>}
          {content?.chunks.map((c) => (
            <Section
              key={c.id}
              chunk={c}
              highlighted={highlightChunkId === c.id || flashId === c.id}
              onCite={onCite}
              onAskAbout={onAskAbout}
              onQuoteToNote={onQuoteToNote}
            />
          ))}
        </div>
      )}
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

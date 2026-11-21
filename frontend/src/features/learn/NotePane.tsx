import { PanelRightClose } from "lucide-react";
import { renderMarkdown } from "@/api/client";
import { useEffect, useRef, useState } from "react";

export type NoteSaveState = "idle" | "saving" | "saved" | "failed";

/** 右侧笔记框（B3-05）：自动保存三态、位置行、选段引用块。 */
export default function NotePane({
  kpPath,
  initial,
  saveState,
  savedAt,
  onChange,
  onGoSource,
  collapsed,
  onToggle,
  textareaRef,
}: {
  kpPath: string[];
  initial: string;
  saveState: NoteSaveState;
  savedAt: string | null;
  onChange: (v: string) => void;
  onGoSource: (chunkId: number) => void;
  collapsed: boolean;
  onToggle: () => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  if (collapsed) {
    return (
      <button
        className="flex h-full w-10 shrink-0 flex-col items-center gap-2 border-l bg-white pt-3 text-xs text-ink-soft hover:bg-black/5"
        onClick={onToggle}
        title="展开笔记"
      >
        <PanelRightClose size={16} className="rotate-180" />
        <span className="[writing-mode:vertical-rl] tracking-widest">笔记</span>
      </button>
    );
  }
  return (
    <div className="flex h-full w-[300px] shrink-0 flex-col border-l bg-white">
      <div className="flex h-11 shrink-0 items-center justify-between border-b px-4">
        <span className="text-sm font-medium">笔记</span>
        <NoteSaveBadge state={saveState} savedAt={savedAt} />
        <button className="text-ink-soft hover:text-ink" onClick={onToggle} title="收起笔记">
          <PanelRightClose size={16} />
        </button>
      </div>
      <div className="border-b bg-paper px-4 py-2 text-xs leading-5 text-ink-soft">
        位置：{kpPath.join(" → ")}
      </div>
      <textarea
        ref={textareaRef}
        className="flex-1 resize-none p-4 text-sm leading-6 outline-none"
        placeholder={"# 我的想法\n随手记；顶部自动带节点位置；从原文选段可一键插入引用块。"}
        value={initial}
        onChange={(e) => onChange(e.target.value)}
        onClick={(e) => {
          // 点击引用块内的「回到原文」锚点链接
          void e;
        }}
      />
      {saveState === "failed" && (
        <div className="border-t bg-red-50 px-4 py-2 text-xs text-red-600">
          保存失败：本地草稿已保留，离开前请重试或复制内容。
        </div>
      )}
      <NotePreview content={initial} onGoSource={onGoSource} />
    </div>
  );
}

function NoteSaveBadge({ state, savedAt }: { state: NoteSaveState; savedAt: string | null }) {
  if (state === "saving") return <span className="text-xs text-ink-soft">保存中…</span>;
  if (state === "failed") return <span className="text-xs text-red-600">保存失败</span>;
  if (state === "saved" && savedAt)
    return <span className="text-xs text-ink-soft">已保存 · {savedAt}</span>;
  return null;
}

/** 底部只读预览：渲染 Markdown（含引用块的原文锚点回跳，链接协议白名单内）。 */
function NotePreview({ content, onGoSource }: { content: string; onGoSource: (chunkId: number) => void }) {
  const [open, setOpen] = useState(false);
  if (!content.trim()) return null;
  return (
    <div className="border-t">
      <button
        className="w-full px-4 py-1.5 text-left text-xs text-ink-soft hover:bg-black/5"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "收起预览 ▾" : "预览笔记（引用块可回跳原文）▸"}
      </button>
      {open && (
        <div
          className="max-h-52 overflow-y-auto px-4 pb-3 text-sm leading-6"
          onClick={(e) => {
            const el = (e.target as HTMLElement).closest("[data-chunk]");
            if (el) onGoSource(Number(el.getAttribute("data-chunk")));
          }}
          dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
        />
      )}
    </div>
  );
}

/** 在光标处插入引用块（来源文本快照 + chunk 锚点）。 */
export function insertQuoteAtCursor(
  textarea: HTMLTextAreaElement | null,
  quote: string,
  chunkId: number,
  title: string,
): string {
  const current = textarea?.value ?? "";
  const pos = textarea?.selectionStart ?? current.length;
  const safe = quote.replace(/\n+/g, " ").slice(0, 200);
  const block = `> ${title}：${safe} [回到原文](#chunk-${chunkId})\n\n`;
  const before = current.slice(0, pos);
  const after = current.slice(pos);
  return `${before}${block}${after}`;
}

export function useDebouncedSave(
  value: string,
  save: (v: string) => Promise<void>,
  delay = 800,
): [NoteSaveState, string | null] {
  const [state, setState] = useState<NoteSaveState>("idle");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setState("saving");
    const t = setTimeout(() => {
      save(value)
        .then(() => {
          setState("saved");
          const now = new Date();
          setSavedAt(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`);
        })
        .catch(() => setState("failed"));
    }, delay);
    return () => clearTimeout(t);
     
  }, [value, delay]);

  return [state, savedAt];
}

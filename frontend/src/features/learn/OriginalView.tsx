import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChunkPayload } from "@/api/client";

/** 原文视图定位目标（B6-07）：由当前切片的 location 派生。 */
export interface OriginalTarget {
  chunkId: number;
  page?: number; // pdf：0 基起始页
  line?: number; // txt/md：1 基起始行
  href?: string; // epub：zip 内文档路径
  anchor?: string; // epub：标题锚点
  snippet?: string; // 首段文本（epub/md 段落级定位细化）
}

type ChunkLocation = {
  type?: string;
  page_start?: number;
  page_end?: number;
  line_start?: number;
  line_end?: number;
  href?: string;
  anchor?: string;
};

/** 切片 → 定位目标；没有可用坐标的返回 null（原文视图给「位置不可用」）。 */
export function toTarget(chunk: ChunkPayload): OriginalTarget | null {
  const loc = (chunk.location ?? {}) as ChunkLocation;
  if (loc.type === "pdf" && typeof loc.page_start === "number")
    return { chunkId: chunk.id, page: loc.page_start, snippet: firstSnippet(chunk.content) };
  if (loc.type === "lines" && typeof loc.line_start === "number")
    return { chunkId: chunk.id, line: loc.line_start };
  if (loc.type === "epub" && loc.href)
    return { chunkId: chunk.id, href: loc.href, anchor: loc.anchor, snippet: firstSnippet(chunk.content) };
  return null;
}

/** 首段文本片段（去空白取前 24 字），EPUB/MD 用它把定位细化到段落。 */
function firstSnippet(content: string): string {
  const first = content.split(/\n\n+/)[0] ?? "";
  return first.replace(/\s+/g, "").slice(0, 24);
}

const norm = (s: string) => s.replace(/\s+/g, "");

function chunkByPage(chunks: ChunkPayload[], page: number): number | null {
  for (const c of chunks) {
    const loc = (c.location ?? {}) as ChunkLocation;
    const end = typeof loc.page_end === "number" ? loc.page_end : loc.page_start;
    if (loc.type === "pdf" && typeof loc.page_start === "number" && page >= loc.page_start && page <= (end ?? loc.page_start))
      return c.id;
  }
  return null;
}

function chunkByLine(chunks: ChunkPayload[], line: number): number | null {
  for (const c of chunks) {
    const loc = (c.location ?? {}) as ChunkLocation;
    const end = typeof loc.line_end === "number" ? loc.line_end : loc.line_start;
    if (loc.type === "lines" && typeof loc.line_start === "number" && line >= loc.line_start && line <= (end ?? loc.line_start))
      return c.id;
  }
  return null;
}

/** 可见文本 → 切片：取前缀片段与任一切片内容匹配（EPUB/MD 双向定位）。 */
function chunkByText(chunks: ChunkPayload[], text: string | null): number | null {
  if (!text) return null;
  const needle = norm(text).slice(0, 24);
  if (needle.length < 6) return null;
  for (const c of chunks) if (norm(c.content).includes(needle)) return c.id;
  return null;
}

/** 文档序遍历块级元素，取「包含片段且文本最短」的最内层块（定位细化到段落）。 */
function findBlockByText(root: HTMLElement, snippet?: string): Element | null {
  if (!snippet) return null;
  const needle = norm(snippet).slice(0, 24);
  if (!needle) return null;
  let best: Element | null = null;
  let bestLen = Number.POSITIVE_INFINITY;
  for (const el of root.querySelectorAll("p,h1,h2,h3,h4,h5,h6,li,blockquote,pre,td,figcaption")) {
    const t = norm(el.textContent ?? "");
    if (t.includes(needle) && t.length < bestLen) {
      best = el;
      bestLen = t.length;
    }
  }
  return best;
}

/** 视口顶边压住的第一个块级元素的文本（反向定位的匹配源）。 */
function textAtTop(root: HTMLElement, topEdge: number): string | null {
  for (const el of root.querySelectorAll("p,h1,h2,h3,h4,h5,h6,li,blockquote,pre,td,figcaption")) {
    const r = el.getBoundingClientRect();
    if (r.bottom > topEdge && r.height > 0) return el.textContent;
  }
  return null;
}

function OriginalError({ text, detail }: { text: string; detail?: string | null }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
      <p className="text-sm text-red-600">{text}</p>
      {detail && <p className="text-xs text-ink-soft">{detail}</p>}
      <p className="text-xs text-ink-soft">解析文本视图不受影响，可切回继续学习。</p>
    </div>
  );
}

/** 拉取 /original 下发的规范化文本（与切片同源，行号才对得上 location）。 */
function useOriginalFetch(sourceId: number) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    setText(null);
    setError(null);
    fetch(`/api/sources/${sourceId}/original`, { signal: ctrl.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "原文件不存在" : `读取失败（${r.status}）`);
        return r.text();
      })
      .then(setText)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "读取失败");
      });
    return () => ctrl.abort();
  }, [sourceId]);
  return { text, error };
}

export default function OriginalView({
  sourceId,
  sourceType,
  chunks,
  target,
  onLocate,
}: {
  sourceId: number;
  sourceType: string;
  chunks: ChunkPayload[];
  target: OriginalTarget | null;
  onLocate: (chunkId: number | null) => void;
}) {
  if (sourceType === "pdf" && target)
    return <PdfView sourceId={sourceId} chunks={chunks} target={target} onLocate={onLocate} />;
  if (sourceType === "txt" && target)
    return <TxtView sourceId={sourceId} chunks={chunks} target={target} onLocate={onLocate} />;
  if (sourceType === "md" && target)
    return <MdView sourceId={sourceId} chunks={chunks} target={target} onLocate={onLocate} />;
  if (sourceType === "epub" && target)
    return <EpubView sourceId={sourceId} chunks={chunks} target={target} onLocate={onLocate} />;
  if (!target) return <OriginalError text="该节点切片没有原文位置信息，无法定位原文。" />;
  return <OriginalError text={`该格式（${sourceType}）暂无原文视图。`} />;
}

/* ---------- PDF：pdf.js 整页渲染（图片天然在页上，决策 #41） ---------- */

let pdfjsPromise: Promise<typeof import("pdfjs-dist")> | null = null;
async function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import("pdfjs-dist").then((mod) => {
      // worker 地址用 ?url 导入：build 下 new URL(<裸包名>) 不会被 Vite 解析
      mod.GlobalWorkerOptions.workerSrc = workerUrl;
      return mod;
    });
  }
  return pdfjsPromise;
}

function PdfView({
  sourceId,
  chunks,
  target,
  onLocate,
}: {
  sourceId: number;
  chunks: ChunkPayload[];
  target: OriginalTarget;
  onLocate: (chunkId: number | null) => void;
}) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState(1); // 1 基展示页码
  const [heights, setHeights] = useState<Record<number, number>>({}); // 已渲染页的真实高度
  const scrollRef = useRef<HTMLDivElement>(null);
  // 用户未滚动前，布局再变（懒渲染页高逐个落地）都重新对齐目标页；用户一滚即接管
  const userScrolled = useRef(false);
  const jumpEcho = useRef(0); // 程序设 scrollTop 后的回声窗口
  const reportHeight = useCallback((n: number, h: number) => {
    setHeights((m) => (m[n] === h ? m : { ...m, [n]: h }));
    if (n === 1) setUniformHeight((u) => (u === h ? u : h)); // 真实页高回填，纠正常数估算的偏差
  }, []);

  // 反向定位：视口顶部的页码 → 切片
  const onScroll = useCallback(() => {
    const root = scrollRef.current;
    if (!root) return;
    if (Date.now() - jumpEcho.current < 250) return; // 程序跳页的滚动回声，不重算当前页
    // 与正向定位同一套常量布局：第 n 页内容区间 [sticky+12+(n-1)×(H+12), +H)
    const sticky = root.querySelector("[data-pdf-sticky]") as HTMLElement | null;
    const stickyH = sticky ? sticky.offsetHeight : 0;
    const pages = Array.from(root.querySelectorAll("[data-page]")) as HTMLElement[];
    const uniform = pages[0]?.offsetHeight ?? 0;
    const edge = root.scrollTop + stickyH + 20;
    let page = pages.length;
    for (let i = 0; i < pages.length; i++) {
      if (edge < stickyH + 12 + (i + 1) * (uniform + 12)) {
        page = i + 1;
        break;
      }
    }
    setCurrent(page);
    onLocate(chunkByPage(chunks, page - 1));
  }, [chunks, onLocate]);
  const pending = useRef(0);
  const scrollHandler = useCallback(() => {
    if (pending.current) return;
    pending.current = requestAnimationFrame(() => {
      pending.current = 0;
      onScroll();
    });
  }, [onScroll]);
  useEffect(() => () => cancelAnimationFrame(pending.current), []);

  useEffect(() => {
    let cancelled = false;
    let task: PDFDocumentLoadingTask | null = null;
    loadPdfjs()
      .then((mod) => {
        task = mod.getDocument({ url: `/api/sources/${sourceId}/original` });
        return task.promise;
      })
      .then((d) => {
        if (cancelled) void task?.destroy();
        else setDoc(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "读取失败");
      });
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [sourceId]);

  // 以第 1 页高度给全部页占位（按滚动容器即时宽度）：懒渲染下先跳页再等真高度会被上方页面把目标顶走
  const [uniformHeight, setUniformHeight] = useState<number | null>(null);
  useEffect(() => {
    if (!doc) return;
    const root = scrollRef.current;
    let alive = true;
    const compute = () => {
      const holder = root?.querySelector("[data-pages]") as HTMLElement | null;
      const w = holder ? Math.floor(holder.getBoundingClientRect().width) : 0;
      if (w <= 0 || !alive) return;
      doc.getPage(1).then((p) => {
        if (!alive) return;
        const base = p.getViewport({ scale: 1 });
        setUniformHeight(Math.ceil((w / base.width) * base.height));
      });
    };
    compute();
    window.addEventListener("resize", compute);
    return () => {
      alive = false;
      window.removeEventListener("resize", compute);
    };
  }, [doc]);

  // 正向定位：目标 scrollTop 由常量布局算出（sticky 条 + 12 内边距 + (n-1)×(页高+12 间距)），
  // 不依赖测量时机——懒渲染各阶段布局一致，构造上确定；用户滚轮/按键/触摸即接管
  const page = (target.page ?? 0) + 1;
  useEffect(() => {
    if (!doc || uniformHeight === null || userScrolled.current) return;
    const root = scrollRef.current;
    if (!root) return;
    const sticky = root.querySelector("[data-pdf-sticky]") as HTMLElement | null;
    const pageH = heights[1] ?? uniformHeight; // 占位估算会被第 1 页真实高度回填
    const targetTop = (sticky ? sticky.offsetHeight : 0) + 12 + (page - 1) * (pageH + 12);
    if (Math.abs(root.scrollTop - targetTop) > 40) {
      // 尾页内容不足一屏时 scrollTop 会被视口钳制，页无法贴顶：
      // 此时「当前页」仍按目标页计（阅读器惯例），并抑制紧随其后的滚动回声重算
      jumpEcho.current = Date.now();
      root.scrollTop = targetTop;
      setCurrent(page);
    }
    onLocate(target.chunkId);
  }, [doc, uniformHeight, heights, page, target.chunkId, onLocate]);

  if (error) return <OriginalError text="原文文件读取失败。" detail={error} />;
  return (
    <div
      ref={scrollRef}
      onScroll={scrollHandler}
      onWheel={() => {
        userScrolled.current = true;
      }}
      onKeyDown={() => {
        userScrolled.current = true;
      }}
      onTouchStart={() => {
        userScrolled.current = true;
      }}
      className="h-full overflow-y-auto"
    >
      {doc ? (
        <>
          <div data-pdf-sticky className="sticky top-0 z-10 flex items-center justify-between border-b bg-white/95 px-3 py-1.5 text-xs text-ink-soft">
            <span aria-label="PDF 页码">
              第 {current} 页 / 共 {doc.numPages} 页
            </span>
            <div className="flex gap-1">
              <button
                className="rounded border px-2 py-0.5 text-xs hover:bg-black/5 disabled:opacity-40"
                disabled={current <= 1}
                onClick={() => scrollRef.current?.querySelector(`[data-page="${current - 1}"]`)?.scrollIntoView()}
              >
                上一页
              </button>
              <button
                className="rounded border px-2 py-0.5 text-xs hover:bg-black/5 disabled:opacity-40"
                disabled={current >= doc.numPages}
                onClick={() => scrollRef.current?.querySelector(`[data-page="${current + 1}"]`)?.scrollIntoView()}
              >
                下一页
              </button>
            </div>
          </div>
          <div data-pages className="space-y-3 p-3">
            {Array.from({ length: doc.numPages }, (_, i) => (
              <PdfPage
                key={i}
                pdf={doc}
                pageNumber={i + 1}
                reserve={uniformHeight}
                onRendered={reportHeight}
              />
            ))}
          </div>
        </>
      ) : (
        <p className="px-4 py-6 text-sm text-ink-soft">正在打开原文…</p>
      )}
    </div>
  );
}

/** 单页画布：进视口才渲染（懒渲染），离开清空释放内存；真实高度回报给父级做对齐。 */
function PdfPage({
  pdf,
  pageNumber,
  reserve,
  onRendered,
}: {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  reserve: number | null;
  onRendered: (pageNumber: number, height: number) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [reserved, setReserved] = useState<number | null>(reserve);
  useEffect(() => {
    if (reserve !== null) setReserved(reserve);
  }, [reserve]);
  const taskRef = useRef<{ cancel: () => void } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    let cancelled = false;
    const io = new IntersectionObserver(
      (es) => {
        for (const en of es) {
          if (en.isIntersecting) {
            void (async () => {
              try {
                const page = await pdf.getPage(pageNumber);
                if (cancelled) return;
                const base = page.getViewport({ scale: 1 });
                // 渲染时即时测量自身宽度（布局像素，不经状态转发也不受合成缩放影响）
                const w = el.clientWidth;
                if (w <= 0) return;
                const vp = page.getViewport({ scale: w / base.width });
                const h = Math.ceil(vp.height);
                setReserved(h);
                const canvas = canvasRef.current;
                const ctx = canvas?.getContext("2d");
                if (!canvas || !ctx) return;
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                canvas.width = Math.floor(vp.width * dpr);
                canvas.height = Math.floor(vp.height * dpr);
                taskRef.current?.cancel();
                const task = page.render({
                  canvas,
                  canvasContext: ctx,
                  viewport: vp,
                  transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
                });
                taskRef.current = task;
                await task.promise;
                if (!cancelled) onRendered(pageNumber, h);
              } catch {
                /* 渲染被取消或页损坏：保留占位，不中断整册 */
              }
            })();
          } else {
            taskRef.current?.cancel();
            const canvas = canvasRef.current;
            if (canvas) {
              canvas.width = 0;
              canvas.height = 0;
            }
          }
        }
      },
      { rootMargin: "400px 0px" },
    );
    io.observe(el);
    return () => {
      cancelled = true;
      io.disconnect();
      taskRef.current?.cancel();
    };
  }, [pdf, pageNumber, reserve, onRendered]);

  return (
    <div
      ref={wrapRef}
      data-page={pageNumber}
      className="bg-white shadow-sm ring-1 ring-line"
      style={{ height: reserved ?? undefined, minHeight: 120 }}
    >
      <canvas ref={canvasRef} className="block w-full" />
    </div>
  );
}

/* ---------- TXT：规范化文本按行渲染，行号即 location 坐标 ---------- */

function TxtView({
  sourceId,
  chunks,
  target,
  onLocate,
}: {
  sourceId: number;
  chunks: ChunkPayload[];
  target: OriginalTarget;
  onLocate: (chunkId: number | null) => void;
}) {
  const { text, error } = useOriginalFetch(sourceId);
  const lines = useMemo(() => (text ?? "").split("\n"), [text]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const onScroll = useCallback(() => {
    const root = scrollRef.current;
    if (!root) return;
    const edge = root.getBoundingClientRect().top + 8;
    const kids = root.querySelectorAll("[data-line]");
    // 二分找顶边压住的行（offsetTop 单调递增）
    let lo = 0;
    let hi = kids.length - 1;
    let found = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if ((kids[mid] as HTMLElement).getBoundingClientRect().bottom > edge) {
        found = mid;
        hi = mid - 1;
      } else lo = mid + 1;
    }
    onLocate(chunkByLine(chunks, found + 1));
  }, [chunks, onLocate]);
  const pending = useRef(0);
  const scrollHandler = useCallback(() => {
    if (pending.current) return;
    pending.current = requestAnimationFrame(() => {
      pending.current = 0;
      onScroll();
    });
  }, [onScroll]);
  useEffect(() => () => cancelAnimationFrame(pending.current), []);

  useEffect(() => {
    if (text === null) return;
    scrollRef.current?.querySelector(`[data-line="${target.line ?? 1}"]`)?.scrollIntoView({ block: "start" });
    onLocate(target.chunkId); // 短文可能不产生滚动事件，前向定位后立即回报位置
  }, [text, target.line, target.chunkId, onLocate]);

  if (error) return <OriginalError text="原文文件读取失败。" detail={error} />;
  return (
    <div ref={scrollRef} onScroll={scrollHandler} className="h-full overflow-y-auto">
      {text === null ? (
        <p className="px-4 py-6 text-sm text-ink-soft">正在打开原文…</p>
      ) : (
        <pre className="whitespace-pre-wrap px-4 py-3 font-sans text-sm leading-7">
          {lines.map((line, i) => (
            <div key={i} data-line={i + 1}>
              {line === "" ? "\u00A0" : line}
            </div>
          ))}
        </pre>
      )}
    </div>
  );
}

/* ---------- MD：react-markdown 渲染，外链图可见、本地相对路径图占位 ---------- */

function MdView({
  sourceId,
  chunks,
  target,
  onLocate,
}: {
  sourceId: number;
  chunks: ChunkPayload[];
  target: OriginalTarget;
  onLocate: (chunkId: number | null) => void;
}) {
  const { text, error } = useOriginalFetch(sourceId);
  const scrollRef = useRef<HTMLDivElement>(null);

  const onScroll = useCallback(() => {
    const root = scrollRef.current;
    if (!root) return;
    const edge = root.getBoundingClientRect().top + 8;
    onLocate(chunkByText(chunks, textAtTop(root, edge)));
  }, [chunks, onLocate]);
  const pending = useRef(0);
  const scrollHandler = useCallback(() => {
    if (pending.current) return;
    pending.current = requestAnimationFrame(() => {
      pending.current = 0;
      onScroll();
    });
  }, [onScroll]);
  useEffect(() => () => cancelAnimationFrame(pending.current), []);

  // MD 渲染块不带行号：首段文本匹配定位（与反向同源，匹配不到留在原地）
  useEffect(() => {
    if (text === null) return;
    const root = scrollRef.current;
    if (!root) return;
    findBlockByText(root, target.snippet)?.scrollIntoView({ block: "start" });
    onLocate(target.chunkId);
  }, [text, target.snippet, target.chunkId, onLocate]);

  if (error) return <OriginalError text="原文文件读取失败。" detail={error} />;
  return (
    <div ref={scrollRef} onScroll={scrollHandler} className="h-full overflow-y-auto">
      {text === null ? (
        <p className="px-4 py-6 text-sm text-ink-soft">正在打开原文…</p>
      ) : (
        <div className="prose-book px-4 py-3">
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{ img: ({ src, alt }) => <MdImg src={typeof src === "string" ? src : ""} alt={alt ?? ""} /> }}
          >
            {text}
          </Markdown>
        </div>
      )}
    </div>
  );
}

function MdImg({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  if (!/^(https?:|data:image\/)/i.test(src)) {
    return (
      <div className="my-2 rounded-md border border-dashed px-3 py-2 text-xs text-ink-soft" data-md-img-placeholder={src}>
        本地图片 {src}：单文件导入不支持引用本地图片，此处占位。
      </div>
    );
  }
  if (failed) {
    return (
      <div className="my-2 rounded-md border border-dashed px-3 py-2 text-xs text-ink-soft">图片加载失败：{src}</div>
    );
  }
  return <img src={src} alt={alt} className="my-2 max-w-full" loading="lazy" onError={() => setFailed(true)} />;
}

/* ---------- EPUB：消毒片段渲染 + 首段文本/锚点定位（技术设计 §8.1） ---------- */

function EpubView({
  sourceId,
  chunks,
  target,
  onLocate,
}: {
  sourceId: number;
  chunks: ChunkPayload[];
  target: OriginalTarget;
  onLocate: (chunkId: number | null) => void;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const assetPath = target.href?.split("/").map(encodeURIComponent).join("/");

  const onScroll = useCallback(() => {
    const root = scrollRef.current;
    if (!root) return;
    const edge = root.getBoundingClientRect().top + 8;
    onLocate(chunkByText(chunks, textAtTop(root, edge)));
  }, [chunks, onLocate]);
  const pending = useRef(0);
  const scrollHandler = useCallback(() => {
    if (pending.current) return;
    pending.current = requestAnimationFrame(() => {
      pending.current = 0;
      onScroll();
    });
  }, [onScroll]);
  useEffect(() => () => cancelAnimationFrame(pending.current), []);

  useEffect(() => {
    if (!assetPath) {
      setError("该切片没有原文文件位置。");
      setHtml(null);
      return;
    }
    const ctrl = new AbortController();
    setHtml(null);
    setError(null);
    fetch(`/api/sources/${sourceId}/assets/${assetPath}`, { signal: ctrl.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 404 ? "原文文件不存在" : `读取失败（${r.status}）`);
        return r.text();
      })
      .then(setHtml)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "读取失败");
      });
    return () => ctrl.abort();
  }, [sourceId, assetPath]);

  // 先按切片首段文本细化到段落；匹配不到退到标题锚点
  useEffect(() => {
    if (html === null) return;
    const root = scrollRef.current;
    if (!root) return;
    const node =
      findBlockByText(root, target.snippet) ??
      (target.anchor ? root.querySelector(`#${CSS.escape(target.anchor)}`) : null);
    node?.scrollIntoView({ block: "start" });
    onLocate(target.chunkId);
  }, [html, target.snippet, target.anchor, target.chunkId, onLocate]);

  if (error) return <OriginalError text="原文读取失败。" detail={error} />;
  return (
    <div ref={scrollRef} onScroll={scrollHandler} className="h-full overflow-y-auto">
      {html === null ? (
        <p className="px-4 py-6 text-sm text-ink-soft">正在打开原文…</p>
      ) : (
        // 后端 nh3 白名单消毒后的片段（EPUB 属外部输入，前端不再二次处理，§8.3）
        <div className="prose-book px-4 py-3" dangerouslySetInnerHTML={{ __html: html }} />
      )}
    </div>
  );
}

import { ChevronRight } from "lucide-react";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import type { KnowledgeNode } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn, STATUS_LABEL } from "@/lib/utils";
import { nextChapterOf, NodeStatusDot } from "./TreePage";

interface PathStop {
  node: KnowledgeNode;
  parent: KnowledgeNode | null;
}

/** 章内路径（P03-C）：纵向路线，起点在底部；已走段金色流光、未走段暗虚线。 */
export default function ChapterPathView({
  studyId,
  chapter,
  nodes,
  selectedId,
  onSelect,
  onBackToMap,
  onEnterChapter,
}: {
  studyId: number;
  chapter: KnowledgeNode;
  nodes: KnowledgeNode[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onBackToMap: () => void;
  onEnterChapter: (chapter: KnowledgeNode) => void;
}) {
  const stops = buildStops(chapter);
  const nextChapter = nextChapterOf(nodes, chapter.id);
  const containerRef = useRef<HTMLDivElement>(null);
  const reversed = stops.slice().reverse();

  // 默认滚到当前进度节点（首个未点亮学习单元）
  useEffect(() => {
    const firstOpen = stops.findIndex((s) => s.node.status !== "lighted");
    const idx = firstOpen === -1 ? stops.length - 1 : firstOpen;
    const target = reversed[idx];
    if (!target) return;
    const el = containerRef.current?.querySelector(`[data-stop="${target.node.id}"]`);
    el?.scrollIntoView({ block: "center" });
  }, [stops, reversed]);

  const lighted = chapter.lighted_count ?? 0;
  const total = chapter.valid_total ?? 0;

  return (
    <div className="rounded-lg border bg-white">
      <div className="flex items-center gap-2 border-b px-5 py-3 text-sm">
        <span className="font-semibold">{chapter.name}</span>
        <span className="text-ink-soft">
          {lighted} / {total} 已点亮
        </span>
      </div>
      <div ref={containerRef} className="max-h-[62vh] overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-lg">
          {reversed.map((stop, ri) => {
            const below = reversed[ri - 1];
            // 下方节点已点亮 → 这一段是“已走路径”（金色流光）；否则暗虚线
            const walked = below ? below.node.status === "lighted" : true;
            const showParentLabel =
              stop.parent && ri > 0 && reversed[ri - 1].parent?.id !== stop.parent?.id;
            return (
              <div key={stop.node.id}>
                {showParentLabel && (
                  <div className="my-1 text-center text-xs text-ink-soft">── {stop.parent!.name} ──</div>
                )}
                <PathRow
                  studyId={studyId}
                  stop={stop}
                  walked={walked}
                  selected={selectedId === stop.node.id}
                  onSelect={onSelect}
                />
              </div>
            );
          })}
          <div className="mt-6 flex items-center justify-between text-sm">
            <button className="flex items-center gap-1 text-ink-soft hover:text-ink" onClick={onBackToMap}>
              返回星盘
            </button>
            {nextChapter && (
              <button
                className="flex items-center gap-1 text-ink-soft hover:text-ink"
                onClick={() => onEnterChapter(nextChapter)}
              >
                下一章 <ChevronRight size={14} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function buildStops(chapter: KnowledgeNode): PathStop[] {
  const stops: PathStop[] = [];
  const walk = (node: KnowledgeNode, parent: KnowledgeNode | null) => {
    if (node.is_learning_unit) stops.push({ node, parent });
    for (const child of node.children ?? []) walk(child, node);
  };
  for (const child of chapter.children ?? []) walk(child, chapter.parent_id === null ? null : chapter);
  if (!stops.length && chapter.is_learning_unit) stops.push({ node: chapter, parent: null });
  return stops.sort((a, b) => a.node.sort_order - b.node.sort_order);
}

function PathRow({
  studyId,
  stop,
  walked,
  selected,
  onSelect,
}: {
  studyId: number;
  stop: PathStop;
  walked: boolean;
  selected: boolean;
  onSelect: (id: number) => void;
}) {
  const nav = useNavigate();
  const node = stop.node;
  return (
    <div className="flex flex-col">
      {/* 连线段：从下方爬上来 */}
      <div className="flex justify-center">
        <div
          className={cn(
            "h-6 w-[3px] rounded",
            walked ? "bo-flow" : "border-l-2 border-dashed border-line",
          )}
        />
      </div>
      <div
        className={cn(
          "flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 hover:bg-black/5",
          selected && "bg-blue-50",
          node.status === "learning" && "bo-breathe rounded-full",
        )}
        data-stop={node.id}
        onClick={() => onSelect(node.id)}
      >
        <NodeStatusDot status={node.status} />
        <span className={cn("flex-1 truncate text-sm", node.excluded && "text-ink-soft line-through")}>
          {node.name}
          {node.origin === "ai_split" && <span className="ml-1 text-xs text-violet-600">AI 拆分</span>}
        </span>
        <span className="text-xs text-ink-soft">{STATUS_LABEL[node.status ?? ""] ?? ""}</span>
        {node.is_learning_unit && !node.excluded && (
          <Button
            size="sm"
            variant={node.status === "lighted" ? "outline" : "default"}
            onClick={(e) => {
              e.stopPropagation();
              nav(`/studies/${studyId}/learn/${node.id}`);
            }}
          >
            {node.status === "lighted" ? "重新测验" : node.status === "learning" ? "继续学习" : "开始学习"}
          </Button>
        )}
      </div>
    </div>
  );
}

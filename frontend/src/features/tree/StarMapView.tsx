import { Crown } from "lucide-react";
import { useMemo } from "react";
import type { KnowledgeNode, KnowledgeTree } from "@/api/client";
import { cn } from "@/lib/utils";

/** 章节星盘（P03-C 星盘视图）：章星分区 / 星环进度 / 金冠 / 当前章呼吸蓝光。 */
export default function StarMapView({
  tree,
  onSelect,
  onEnterChapter,
}: {
  tree: KnowledgeTree;
  onSelect: (id: number) => void;
  onEnterChapter: (chapter: KnowledgeNode) => void;
}) {
  const groups = useMemo(() => buildGroups(tree.nodes), [tree]);

  return (
    <div className="rounded-lg border bg-white p-6">
      {groups.map((g) => (
        <section key={g.key} className="mb-8 last:mb-2">
          {g.name && (
            <h3 className="mb-4 text-sm font-semibold tracking-wide text-ink-soft">{g.name}</h3>
          )}
          <div className="flex flex-wrap gap-6">
            {g.chapters.map((ch) => (
              <ChapterStar key={ch.id} chapter={ch} onSelect={onSelect} onEnter={onEnterChapter} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

interface StarGroup {
  key: string;
  name: string | null;
  chapters: KnowledgeNode[];
}

function buildGroups(roots: KnowledgeNode[]): StarGroup[] {
  // 按书序原位排布（BUG-004）：散章在书中的位置决定其分区位置，部分组不前移
  const out: StarGroup[] = [];
  let loose: KnowledgeNode[] = [];
  const flush = () => {
    if (loose.length) out.push({ key: `loose-${loose[0].id}`, name: null, chapters: loose });
    loose = [];
  };
  for (const root of roots) {
    const childChapters = (root.children ?? []).filter((c) => c.is_chapter);
    if (root.origin === "ai_group" && childChapters.length) {
      flush();
      out.push({ key: `g${root.id}`, name: root.name, chapters: childChapters });
    } else if (root.is_chapter) {
      loose.push(root);
    }
  }
  flush();
  return out;
}

function ChapterStar({
  chapter,
  onSelect,
  onEnter,
}: {
  chapter: KnowledgeNode;
  onSelect: (id: number) => void;
  onEnter: (chapter: KnowledgeNode) => void;
}) {
  // 无子节点的章自身是学习单元：星环按 0/1 或 1/1（页面清单 C）
  const lighted = chapter.lighted_count ?? (chapter.status === "lighted" ? 1 : 0);
  const total = chapter.valid_total ?? 1;
  const full = total > 0 && lighted === total;
  const excluded = chapter.excluded;
  const percent = total ? (lighted / total) * 100 : 0;
  return (
    <div
      className={cn(
        "group relative w-36 cursor-pointer text-center",
        excluded && "opacity-45",
      )}
      onClick={() => {
        if (excluded) {
          onSelect(chapter.id);
          return;
        }
        onEnter(chapter);
      }}
    >
      <div className="relative mx-auto h-20 w-20">
        {/* 星环 */}
        <div
          className="bo-star-ring absolute inset-0"
          style={{
            background: `conic-gradient(var(--color-lighted) ${percent}%, #e5e1d8 ${percent}%)`,
          }}
        />
        <div
          className={cn(
            "absolute inset-[5px] flex items-center justify-center rounded-full bg-white text-lg",
            !excluded && "bo-breathe",
          )}
          title={`${lighted} / ${total}`}
        >
          {full && <Crown className="text-lighted" size={22} />}
          {!full && <span className="text-sm text-ink-soft">{lighted}/{total}</span>}
        </div>
      </div>
      <div
        className={cn(
          "mt-2 line-clamp-2 text-sm",
          excluded && "text-ink-soft line-through",
        )}
      >
        {chapter.name}
      </div>
      {excluded && <div className="text-xs text-ink-soft">已排除 · 点击查看</div>}
      {!excluded && chapter.lighted_count !== null && (
        <div className="text-xs text-ink-soft opacity-0 transition-opacity group-hover:opacity-100">
          进入章内路径 →
        </div>
      )}
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { client, errDetail, flattenTree, type KnowledgeNode, type KnowledgeTree } from "@/api/client";
import { Badge } from "@/components/ui/basics";
import { Button } from "@/components/ui/button";
import { fmtDateTime, STATUS_LABEL } from "@/lib/utils";
import { NodeStatusDot } from "./TreePage";

const ORIGIN_LABEL: Record<string, string> = {
  toc: "原书目录",
  heading: "标题规则识别",
  ai_split: "AI 规划 · 拆分",
  ai_merge: "AI 规划 · 合并",
  ai_organize: "AI 规划 · 章内组织",
  ai_group: "AI 规划 · 部分分组",
  manual: "用户修改",
};

/** 详情面板（星盘与工作树共用）：来源与识别、学习数据、原文引用与主动作。 */
export default function DetailPanel({
  studyId,
  node,
  tree,
  onClose,
}: {
  studyId: number;
  node: KnowledgeNode;
  tree?: KnowledgeTree;
  onClose: () => void;
}) {
  const nav = useNavigate();
  // 面包屑：从整树找祖先
  const { data: fullTree } = useQuery({
    queryKey: ["tree", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/knowledge", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    initialData: tree,
    enabled: !tree,
  });
  const breadcrumb = useBreadcrumb(fullTree, node.id);

  const { data: content } = useQuery({
    queryKey: ["kp-content", node.id],
    queryFn: async () => {
      const res = await client.GET("/api/kps/{kp_id}/content", {
        params: { path: { kp_id: node.id } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: node.is_learning_unit,
  });

  // 排除的叶子节点本是学习单元（排除使其 is_learning_unit 置 false），不能渲染成"容器"（BUG-005）
  const wasLearningUnit = node.excluded && (node.children?.length ?? 0) === 0;
  const isContainer = !node.is_learning_unit && !wasLearningUnit;
  return (
    // 停靠在主工作区右列（TreePage 布局承载宽度）：不做浮层，不遮挡行菜单与双进度区
    <aside className="rounded-lg border bg-white p-5 shadow-sm">
      <button className="absolute right-3 top-3 text-ink-soft hover:text-ink" onClick={onClose}>
        <X size={15} />
      </button>
      {breadcrumb.length > 1 && (
        <div className="mb-1 truncate text-xs text-ink-soft">{breadcrumb.slice(0, -1).join(" / ")}</div>
      )}
      <div className="flex items-center gap-2">
        {node.is_learning_unit && <NodeStatusDot status={node.status} />}
        <h3 className="line-clamp-2 font-semibold">{node.name}</h3>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {isContainer ? (
          <Badge>
            容器 · {node.lighted_count ?? 0} / {node.valid_total ?? 0} 点亮
          </Badge>
        ) : wasLearningUnit ? (
          <Badge tone={node.lighted_at ? "gold" : "default"}>学习单元（已排除）</Badge>
        ) : node.status ? (
          <Badge tone={node.status === "lighted" ? "gold" : node.status === "learning" ? "blue" : "default"}>
            {STATUS_LABEL[node.status]}
          </Badge>
        ) : null}
        <Badge tone={node.origin.startsWith("ai_") ? "purple" : "default"}>
          来源：{ORIGIN_LABEL[node.origin] ?? node.origin}
        </Badge>
        <Badge>
          {node.confidence_basis} · {node.confidence >= 0.8 ? "高置信度" : node.confidence >= 0.6 ? "中置信度" : "低置信度"}
        </Badge>
        {node.excluded && <Badge tone="muted">已排除</Badge>}
      </div>
      {node.planning_note && (
        <p className="mt-2 rounded bg-violet-50 p-2 text-xs text-violet-800">AI 调整理由：{node.planning_note}</p>
      )}

      {/* 学习数据（仅学习单元） */}
      {node.is_learning_unit && !node.excluded && (
        <div className="mt-3 space-y-1 text-xs text-ink-soft">
          {node.recent_quiz && (
            <div>
              最近测验 {fmtDateTime(node.recent_quiz.answered_at as unknown as string)} ·{" "}
              <b className={node.recent_quiz.passed ? "text-lighted" : "text-red-600"}>
                {node.recent_quiz.correct_count} / {node.recent_quiz.pass_line}
                {node.recent_quiz.passed ? " 通过" : " 未通过"}
              </b>
            </div>
          )}
          <div>通过线：{passLineText(node)}</div>
          {node.lighted_at && (
            <div>
              点亮时间 {fmtDateTime(node.lighted_at as unknown as string)} ·{" "}
              <button
                className="text-blue-600 hover:underline"
                onClick={() => nav(`/studies/${studyId}/learn/${node.id}`)}
              >
                查看首次通过证据 →
              </button>
            </div>
          )}
        </div>
      )}

      {/* 原文引用 */}
      {content && content.chunks.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-ink-soft">原文引用</div>
          <ul className="mt-1 space-y-0.5 text-xs">
            {content.chunks.slice(0, 4).map((c, i) => (
              <li key={c.id} className="truncate text-ink-soft">
                [{i + 1}] {c.title} · {locText(c.location)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {node.is_learning_unit && !node.excluded && content?.chunks.length === 0 && (
        <p className="mt-3 text-xs text-amber-600">原文准备中，就绪后即可学习。</p>
      )}

      {/* 主动作：容器不提供开始学习（B2-06） */}
      <div className="mt-4 flex flex-wrap gap-2">
        {node.is_learning_unit && !node.excluded ? (
          <Button
            size="sm"
            variant={node.status === "lighted" ? "outline" : "gold"}
            onClick={() => nav(`/studies/${studyId}/learn/${node.id}`)}
          >
            {node.status === "lighted" ? "重新测验（不改变点亮）" : node.status === "learning" ? "继续学习" : "开始学习"} →
          </Button>
        ) : isContainer && !node.excluded ? (
          <span className="text-xs text-ink-soft">容器节点：在左侧展开子节点学习</span>
        ) : (
          <span className="text-xs text-ink-soft">已排除：历史记录只读，可恢复</span>
        )}
      </div>
    </aside>
  );
}

function passLineText(node: KnowledgeNode): string {
  if (node.recent_quiz) {
    const graded = 4; // 通过线按计分题数映射；展示最近测验的通过线
    void graded;
    return `${node.recent_quiz.pass_line + 1} 题对 ${node.recent_quiz.pass_line}（按计分题数固定映射）`;
  }
  return "3 题对 2 / 4 题对 3 / 5 题对 4（按计分题数固定映射）";
}

function locText(loc: Record<string, unknown>): string {
  const t = loc.type;
  if (t === "pdf") return `第 ${(loc.page_start as number) + 1} 页起`;
  if (t === "lines") return `第 ${loc.line_start}–${loc.line_end} 行`;
  if (t === "epub") return `${(loc.href as string).split("/").pop()}`;
  return "位置不可用";
}

function useBreadcrumb(tree: KnowledgeTree | undefined, nodeId: number): string[] {
  const all = tree ? flattenTree(tree.nodes) : [];
  const byId = new Map(all.map((n) => [n.id, n]));
  const path: string[] = [];
  let cur = byId.get(nodeId);
  while (cur) {
    path.unshift(cur.name);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return path;
}

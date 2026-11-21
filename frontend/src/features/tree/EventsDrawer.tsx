import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { client, errDetail } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { fmtDateTime } from "@/lib/utils";

function detail(e: { detail?: Record<string, unknown> }): Record<string, unknown> {
  return e.detail ?? {};
}

function summaryOf(e: { detail?: Record<string, unknown> }): Record<string, number> {
  return (e.detail?.adjust_summary as Record<string, number>) ?? {};
}

const EVENT_LABEL: Record<string, string> = {
  structure_built: "结构识别",
  planning_started: "AI 规划开始",
  planning_finished: "AI 规划完成",
  planning_skipped: "AI 规划跳过",
  planning_failed: "AI 规划失败",
  planning_conflict_skipped: "AI 操作跳过（冲突）",
  kp_created: "AI 建立节点",
  kp_renamed: "重命名",
  kp_excluded: "排除",
  kp_restored: "恢复",
  group_dissolved: "解散部分分组",
  outline_restored: "恢复原目录",
};

/** 结构与规划记录抽屉（P03-E，P1）。 */
export default function EventsDrawer({
  studyId,
  open,
  onOpenChange,
}: {
  studyId: number;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { data: events } = useQuery({
    queryKey: ["outline-events", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/outline/events", {
        params: { path: { study_id: studyId }, query: { limit: 50 } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: open,
  });

  const { data: preview } = useQuery({
    queryKey: ["restore-preview", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/outline/restore-preview", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: open,
  });

  const restore = useMutation({
    mutationFn: async () => {
      const res = await client.POST("/api/studies/{study_id}/outline/restore-original", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: (r) => {
      toast.success(`已恢复原目录（撤销 AI 调整 ${r.ai_adjustments} 项、重命名 ${r.revoked_renames} 项、排除 ${r.revoked_exclusions} 项）`);
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const canRestore = preview?.can_restore;

  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="结构与规划记录">
      {canRestore !== undefined && (
        <div className="mb-4 rounded-md border bg-paper p-3 text-xs">
          <div className="font-medium">恢复原目录</div>
          <p className="mt-1 text-ink-soft">
            将撤销：AI 调整 {preview?.ai_adjustments ?? 0} 项、其后的手动重命名 {preview?.revoked_renames ?? 0} 项、手动排除{" "}
            {preview?.revoked_exclusions ?? 0} 项。
          </p>
          {canRestore ? (
            <Button
              size="sm"
              variant="outline"
              className="mt-2"
              disabled={restore.isPending}
              onClick={() => restore.mutate()}
            >
              {restore.isPending ? "恢复中…" : "恢复原目录"}
            </Button>
          ) : (
            <p className="mt-1 text-amber-600">
              {preview?.planning_running
                ? "拟大纲进行中，暂不可恢复"
                : `已有学习证据（${preview?.evidence_kps.slice(0, 3).join("、")}${(preview?.evidence_kps.length ?? 0) > 3 ? " 等" : ""}），不能整体恢复；请改用逐个排除`}
            </p>
          )}
        </div>
      )}
      <ol className="space-y-3">
        {events?.map((e) => (
          <li key={e.id} className="border-l-2 border-line pl-3">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">{EVENT_LABEL[e.event_type] ?? e.event_type}</span>
              <span className="text-xs text-ink-soft">{actorLabel(e.actor)}</span>
              <span className="ml-auto text-xs text-ink-soft">{fmtDateTime(e.created_at as unknown as string)}</span>
            </div>
            {e.kp_name && <div className="text-xs text-ink-soft">节点：{e.kp_name}</div>}
            {e.event_type === "kp_renamed" && (
              <div className="text-xs text-ink-soft">
                {String(detail(e).before ?? "")} → {String(detail(e).after ?? "")}
              </div>
            )}
            {e.event_type === "planning_conflict_skipped" && (
              <div className="text-xs text-amber-700">
                {String(detail(e).op ?? "")} · 原因：{String(detail(e).reason ?? "")}
              </div>
            )}
            {e.event_type === "planning_finished" && !!detail(e).adjust_summary && (
              <div className="text-xs text-ink-soft">
                {`实际应用 ${Number(summaryOf(e).applied ?? 0)} 项${Number(summaryOf(e).skipped ?? 0) > 0 ? `，跳过 ${Number(summaryOf(e).skipped)} 项` : ""}`}
              </div>
            )}
            {(e.event_type === "kp_excluded" || e.event_type === "kp_restored") &&
              !!detail(e).progress_after && (
                <div className="text-xs text-ink-soft">
                  进度 → {formatProgress(detail(e).progress_after as Record<string, number>)}
                </div>
              )}
          </li>
        ))}
        {events?.length === 0 && <li className="text-sm text-ink-soft">暂无记录。</li>}
      </ol>
    </Sheet>
  );
}

function actorLabel(actor: string): string {
  return { structure: "结构识别", ai: "AI", user: "我", system: "系统" }[actor] ?? actor;
}

function formatProgress(p: Record<string, number>): string {
  if (!p.total) return "—（无有效学习单元）";
  return `${p.lighted} / ${p.total}（${p.percent}%）`;
}

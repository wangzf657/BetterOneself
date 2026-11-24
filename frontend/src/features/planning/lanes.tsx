import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { RotateCw } from "lucide-react";
import { client, errDetail, type PipelineProgress } from "@/api/client";
import { Button } from "@/components/ui/button";
import { usePrecheck } from "@/features/tree/treeApi";

export type PlanDialog = "consume" | "proposal";

/** 双路进度共用：解析、预检、embedding、规划进行中持续刷新，落定后停（B6-05）。 */
export function progressPollInterval(d?: PipelineProgress): number | false {
  if (!d) return 1200;
  if (d.parse.status === "failed") return false;
  const busy =
    d.parse.status !== "parsed" ||
    d.embedding.status === "pending" ||
    d.embedding.status === "running" ||
    d.outline.status === "planning";
  return busy ? 1200 : false;
}

export function useProgress(studyId: number | null) {
  return useQuery<PipelineProgress>({
    queryKey: ["progress", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/progress", {
        params: { path: { study_id: studyId! } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: studyId !== null,
    refetchInterval: (q) => progressPollInterval(q.state.data),
  });
}

interface LaneState {
  label: string;
  tone: "idle" | "doing" | "ok" | "warn" | "fail";
  detail?: string | null;
}

/** embedding 一路（必检）：解析完成后才有意义。 */
export function embedLane(p: PipelineProgress): LaneState {
  if (p.parse.status !== "parsed") return { label: "等待解析完成", tone: "idle" };
  const e = p.embedding;
  switch (e.status) {
    case "pending":
      return { label: "预检中", tone: "doing" };
    case "precheck_failed":
      return { label: "预检失败", tone: "fail", detail: e.error };
    case "running":
      return { label: `进行中 ${e.done}/${e.total}`, tone: "doing" };
    case "ready":
      return { label: "完成", tone: "ok" };
    case "degraded":
      return { label: "降级", tone: "warn", detail: e.error };
    default:
      return { label: "失败", tone: "fail", detail: e.error };
  }
}

/** AI 规划一路：未勾选不显示（B6-05 验收 4）。 */
export function planLane(p: PipelineProgress): LaneState | null {
  if (!p.outline.ai_planning) return null;
  if (p.parse.status !== "parsed") return { label: "等待解析完成", tone: "idle" };
  const o = p.outline;
  switch (o.status) {
    case "structure_ready":
      return { label: "预检中", tone: "doing" };
    case "precheck_failed":
      return { label: "预检失败", tone: "fail", detail: o.error };
    case "precheck_ok":
      return { label: "待确认消耗", tone: "warn", detail: "预检通过，确认后才开始规划" };
    case "planning":
      return o.stage?.phase === "summary"
        ? { label: `章摘要 第 ${o.stage.done}/${o.stage.total} 章`, tone: "doing" }
        : { label: "全局规划中", tone: "doing" };
    case "awaiting_confirm":
      return { label: "待确认树", tone: "warn", detail: "建议已生成，等你逐条确认；确认前原树照常可学" };
    case "ready":
      return { label: "已应用", tone: "ok" };
    case "failed":
      return { label: "失败", tone: "fail", detail: o.error };
    case "skipped":
      return { label: "已跳过", tone: "idle" };
    default:
      return { label: "未开始", tone: "idle" };
  }
}

/** 预检不通的分路提示（B6-02 验收 3）：哪几路不通，就说清那几路的后果。 */
export function precheckHint(p: PipelineProgress): string | null {
  const embedDown = p.embedding.status === "precheck_failed";
  const llmDown = p.outline.status === "precheck_failed";
  if (embedDown && llmDown) return "两路都不通：现在是纯原文阅读模式，原文、笔记与原树学习仍可用。";
  if (embedDown) return "仅资料向量化不通：跨节点检索补足不可用，AI 伴学不受影响。";
  if (llmDown) return "仅 AI 服务不通：无法 AI 伴学与测验，检索不受影响。";
  return null;
}

/** 双进度区（B6-05/06）：两路各自的状态、分路提示与重试入口；一路失败不影响另一路。 */
export function LanesProgress({ studyId, onOpen }: { studyId: number; onOpen?: (d: PlanDialog) => void }) {
  const { data: p } = useProgress(studyId);
  const precheck = usePrecheck(studyId);
  if (!p) return null;
  const status = p.outline.status;
  const plan = planLane(p);
  const hint = precheckHint(p);
  const embedRetry = ["precheck_failed", "failed", "degraded"].includes(p.embedding.status);
  const planAction =
    status === "precheck_failed" || status === "failed"
      ? { label: "重试", run: () => precheck.mutate(undefined, { onSuccess: (r) => r.llm?.ok && onOpen?.("consume") }) }
      : status === "precheck_ok"
        ? { label: "去确认", run: () => onOpen?.("consume") }
        : status === "awaiting_confirm"
          ? { label: "去确认", run: () => onOpen?.("proposal") }
          : undefined;
  return (
    <div className="space-y-1.5">
      <LaneRow
        name="资料向量化"
        state={embedLane(p)}
        action={
          embedRetry
            ? {
                label: "重试",
                run: () => precheck.mutate(["embedding"]),
              }
            : undefined
        }
        busy={precheck.isPending}
      />
      {plan && <LaneRow name="AI 规划" state={plan} action={planAction} busy={precheck.isPending} />}
      {hint && (
        <p className="text-xs text-amber-700">
          {hint}
          <Link to="/settings" className="ml-1 underline">
            查看配置
          </Link>
        </p>
      )}
    </div>
  );
}

const TONE: Record<LaneState["tone"], string> = {
  idle: "text-ink-soft/50",
  doing: "animate-pulse text-blue-600",
  ok: "text-lighted",
  warn: "text-pending",
  fail: "text-red-600",
};
const MARK: Record<LaneState["tone"], string> = { idle: "○", doing: "→", ok: "✓", warn: "!", fail: "✕" };

function LaneRow({
  name,
  state,
  action,
  busy,
}: {
  name: string;
  state: LaneState;
  action?: { label: string; run: () => void };
  busy: boolean;
}) {
  return (
    <div className="text-sm">
      <div className="flex items-center gap-2">
        <span className={TONE[state.tone]}>{MARK[state.tone]}</span>
        <span className={state.tone === "idle" ? "text-ink-soft/60" : ""}>
          {name}：{state.label}
        </span>
        {action && (
          <Button size="sm" variant="outline" className="ml-auto h-7 px-2 text-xs" disabled={busy} onClick={action.run}>
            <RotateCw size={12} /> {action.label}
          </Button>
        )}
      </div>
      {state.detail && (
        <div className={`pl-6 text-xs ${state.tone === "fail" ? "text-red-600" : "text-ink-soft"}`}>{state.detail}</div>
      )}
    </div>
  );
}

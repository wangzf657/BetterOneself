import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { client, errDetail, type PlanningProposalView, type ProposalOp } from "@/api/client";
import { Badge } from "@/components/ui/basics";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useInvalidateTree } from "@/features/tree/treeApi";

const OP_LABEL: Record<string, string> = {
  exclude: "排除",
  split: "拆分",
  merge: "合并",
  group: "分组",
  organize: "章内组织",
};
const OP_TONE: Record<string, "default" | "blue" | "purple" | "amber"> = {
  exclude: "amber",
  split: "blue",
  merge: "blue",
  group: "purple",
  organize: "default",
};

/** 应用前进度影响预估（B6-04 验收 5）。 */
export function impactText(ops: ProposalOp[]): string {
  const count = (kind: string) => ops.filter((o) => o.op === kind).length;
  const parts = [
    count("group") && `分 ${count("group")} 个部分`,
    count("exclude") && `排除 ${count("exclude")} 个节点`,
    count("split") && `拆分 ${count("split")} 处`,
    count("merge") && `合并 ${count("merge")} 处`,
    count("organize") && `章内组织 ${count("organize")} 处`,
  ].filter(Boolean);
  if (!parts.length) return "没有选中任何操作，目录保持原样。";
  return `本次将${parts.join("、")}；点亮进度统计口径不变，学习记录与点亮状态保留。`;
}

/** 规划建议逐条确认（B6-04）：默认全选（有冲突的默认取消），应用所选 / 全部拒绝 / 稍后。 */
export default function ProposalDialog({
  studyId,
  open,
  onOpenChange,
  onDone,
}: {
  studyId: number;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onDone: () => void;
}) {
  const { data: view } = useQuery<PlanningProposalView | null>({
    queryKey: ["proposal", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/planning/proposal", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: open,
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] w-[640px] overflow-y-auto">
        <DialogHeader
          title="确认 AI 规划建议"
          desc="逐条勾选后才应用；有冲突的条目已默认取消。确认之前，原目录照常可以学习。"
        />
        {view ? (
          <ProposalBody
            key={view.proposal_id}
            studyId={studyId}
            view={view}
            onOpenChange={onOpenChange}
            onDone={onDone}
          />
        ) : (
          <p className="text-sm text-ink-soft">正在读取规划建议…</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ProposalBody({
  studyId,
  view,
  onOpenChange,
  onDone,
}: {
  studyId: number;
  view: PlanningProposalView;
  onOpenChange: (v: boolean) => void;
  onDone: () => void;
}) {
  const invalidate = useInvalidateTree();
  const ops = view.operations;
  const [checked, setChecked] = useState<number[]>(() => ops.map((o, i) => (o.flagged ? -1 : i)).filter((i) => i >= 0));
  const [confirmDecline, setConfirmDecline] = useState(false);
  const selected = checked.map((i) => ops[i]).filter(Boolean);
  const toggle = (i: number) =>
    setChecked((c) => (c.includes(i) ? c.filter((x) => x !== i) : [...c, i]));

  const finish = () => {
    invalidate(studyId);
    onOpenChange(false);
    onDone();
  };
  const apply = useMutation({
    mutationFn: async () => {
      const res = await client.POST("/api/studies/{study_id}/planning/proposal/apply", {
        params: { path: { study_id: studyId } },
        body: { proposal_id: view.proposal_id, selected: checked },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: (r) => {
      const skipped = r.skipped.length;
      toast.success(
        skipped
          ? `已应用 ${r.adjust_summary.applied} 项，另有 ${skipped} 项因冲突跳过（见规划记录）`
          : `已应用 ${r.adjust_summary.applied} 项调整`,
      );
      finish();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const decline = useMutation({
    mutationFn: async () => {
      const res = await client.POST("/api/studies/{study_id}/planning/proposal/decline", {
        params: { path: { study_id: studyId } },
        body: { proposal_id: view.proposal_id },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success("已全部拒绝，目录保持原样");
      finish();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const busy = apply.isPending || decline.isPending;

  return (
    <div className="space-y-4 text-sm">
      <div className="rounded-md bg-paper p-3">
        <div className="text-xs text-ink-soft">全书总述（随所选操作一起写入）</div>
        <p className="mt-1">{view.thesis}</p>
      </div>
      <ul className="space-y-2">
        {ops.map((op, i) => (
          <li key={i}>
            <label
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-md border p-3",
                op.flagged && "cursor-not-allowed bg-amber-50/60",
              )}
            >
              <input
                type="checkbox"
                className="mt-1"
                checked={checked.includes(i)}
                disabled={op.flagged || busy}
                onChange={() => toggle(i)}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={OP_TONE[op.op] ?? "default"}>{OP_LABEL[op.op] ?? op.op}</Badge>
                  {op.title && <span className="font-medium">{op.title}</span>}
                </div>
                <div className="text-xs text-ink-soft">涉及：{op.targets.join("、")}</div>
                {op.reason && <div className="mt-1">{op.reason}</div>}
                {op.flagged && (
                  <div className="mt-1 text-xs text-amber-700">已默认取消，不能应用：{op.flag_reason}</div>
                )}
              </div>
            </label>
          </li>
        ))}
        {ops.length === 0 && <li className="text-ink-soft">AI 认为原目录已经贴合书的逻辑，没有提出调整。</li>}
      </ul>
      <p className="text-xs text-ink-soft">{impactText(selected)}</p>
      <div className="flex items-center justify-between gap-2">
        {confirmDecline ? (
          <div className="flex items-center gap-2">
            <Button variant="danger" size="sm" disabled={busy} onClick={() => decline.mutate()}>
              确认全部拒绝
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmDecline(false)}>
              取消
            </Button>
          </div>
        ) : (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmDecline(true)}>
            全部拒绝
          </Button>
        )}
        <div className="flex items-center gap-2">
          <Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
            稍后
          </Button>
          <Button disabled={busy || checked.length === 0} onClick={() => apply.mutate()}>
            {apply.isPending ? "应用中…" : ops.length ? `应用所选（${checked.length}/${ops.length}）` : "应用"}
          </Button>
        </div>
      </div>
    </div>
  );
}

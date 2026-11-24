import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { client, errDetail, type Estimate, type StudyDetail } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/basics";
import { Dialog, DialogContent, DialogHeader } from "@/components/ui/dialog";

const DEFAULT_GOAL = "学透这本书：合上书也能讲清楚";

export function fmtTokens(n: number): string {
  if (n < 10000) return n.toLocaleString("zh-CN");
  const text = (n / 10000).toFixed(n >= 100000 ? 0 : 1);
  return `${text.replace(/\.0$/, "")} 万`;
}

/** 消耗预估与规划启动确认（B6-03）：点「开始规划」才启动；「稍后」不启动、状态保留。 */
export default function PlanConfirmDialog({
  studyId,
  open,
  onOpenChange,
  onStarted,
}: {
  studyId: number;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onStarted: () => void;
}) {
  const { data: study } = useQuery<StudyDetail>({
    queryKey: ["study", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: open,
  });
  const { data: estimate } = useQuery<Estimate>({
    queryKey: ["estimate", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/planning/estimate", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: open,
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader title="开始 AI 规划前，先确认消耗" desc="规划会调用你配置的 AI 服务；确认之前不会产生规划用量。" />
        {study && estimate ? (
          <ConfirmBody
            studyId={studyId}
            estimate={estimate}
            days={study.planned_days}
            goal={study.learning_goal}
            onOpenChange={onOpenChange}
            onStarted={onStarted}
          />
        ) : (
          <p className="text-sm text-ink-soft">正在估算…</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ConfirmBody({
  studyId,
  estimate,
  days,
  goal,
  onOpenChange,
  onStarted,
}: {
  studyId: number;
  estimate: Estimate;
  days: number;
  goal: string;
  onOpenChange: (v: boolean) => void;
  onStarted: () => void;
}) {
  const qc = useQueryClient();
  const [daysText, setDaysText] = useState(String(days));
  const [goalText, setGoalText] = useState(goal);
  const parsedDays = Number(daysText);
  const daysOk = Number.isInteger(parsedDays) && parsedDays >= 1 && parsedDays <= 365;
  const goalOk = goalText.trim().length >= 1 && goalText.trim().length <= 200;
  const [low, high] = estimate.planning_tokens;

  const start = useMutation({
    mutationFn: async () => {
      const res = await client.POST("/api/studies/{study_id}/planning/start", {
        params: { path: { study_id: studyId } },
        body: { planned_days: parsedDays, learning_goal: goalText.trim() },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: (r) => {
      toast.success(r.status === "planning" ? "已开始 AI 规划，可继续用原树学习" : "回到待确认的规划建议");
      onStarted();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["progress", studyId] });
      void qc.invalidateQueries({ queryKey: ["outline-status", studyId] });
      void qc.invalidateQueries({ queryKey: ["study", studyId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-4 text-sm">
      <dl className="space-y-1.5 rounded-md bg-paper p-3">
        <div className="flex justify-between gap-4">
          <dt className="text-ink-soft">资料向量化（已在后台进行，无需确认）</dt>
          <dd>约 {fmtTokens(estimate.embedding_tokens)} token</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-ink-soft">AI 规划（点击后才启动）</dt>
          <dd>
            预计 {fmtTokens(low)}–{fmtTokens(high)} token
          </dd>
        </div>
      </dl>
      <div>
        <Label htmlFor="plan-days">计划学完天数</Label>
        <Input
          id="plan-days"
          type="number"
          min={1}
          max={365}
          value={daysText}
          onChange={(e) => setDaysText(e.target.value)}
        />
      </div>
      <div>
        <Label htmlFor="plan-goal">学习目标</Label>
        <Textarea
          id="plan-goal"
          rows={3}
          maxLength={200}
          value={goalText}
          placeholder={DEFAULT_GOAL}
          onChange={(e) => setGoalText(e.target.value)}
        />
        <div className="mt-1 flex justify-between text-xs text-ink-soft">
          <span>只用来把握规划的取舍尺度，不会生成学习计划或排期。</span>
          <span>{goalText.trim().length}/200</span>
        </div>
      </div>
      <p className="text-xs text-ink-soft">
        规划完成后还会给你一份逐条清单，确认后才会改动目录；现在关闭也不会启动。
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          稍后
        </Button>
        <Button disabled={!daysOk || !goalOk || start.isPending} onClick={() => start.mutate()}>
          {start.isPending ? "启动中…" : "开始规划"}
        </Button>
      </div>
    </div>
  );
}

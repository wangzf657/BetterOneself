import { useState } from "react";
import { usePrecheck } from "@/features/tree/treeApi";
import { useProgress, type PlanDialog } from "./lanes";

/**
 * 两个确认弹窗的开合（B6-03/04）。
 * 导入页自动弹——用户正盯着进度；树页只响应用户操作，关掉后不再弹回。
 */
export function usePlanningDialogs(studyId: number | null, auto: boolean) {
  const { data: progress } = useProgress(studyId);
  const status = progress?.outline.status;
  const [manual, setManual] = useState<PlanDialog | null>(null);
  const [dismissed, setDismissed] = useState<Partial<Record<PlanDialog, boolean>>>({});
  const [expectProposal, setExpectProposal] = useState(false);

  // 状态离开后清掉「稍后」：下一轮（再次预检通过 / 再次生成建议）仍会自动弹出
  const [seen, setSeen] = useState(status);
  if (seen !== status) {
    setSeen(status);
    setDismissed({});
  }

  let dialog = manual;
  if (!dialog) {
    if (status === "precheck_ok" && auto && !dismissed.consume) dialog = "consume";
    else if (status === "awaiting_confirm" && (auto || expectProposal) && !dismissed.proposal)
      dialog = "proposal";
  }
  return {
    status,
    dialog,
    open: setManual,
    close: (which: PlanDialog) => {
      setManual(null);
      setDismissed((d) => ({ ...d, [which]: true }));
    },
    started: () => setExpectProposal(true),
  };
}

export type PlanningDialogs = ReturnType<typeof usePlanningDialogs>;

/** 书菜单「AI 规划…」（B6-06）：按当前状态直达对应确认页，否则先预检、通过再进消耗确认。 */
export function usePlanningEntry(studyId: number, dialogs: PlanningDialogs) {
  const precheck = usePrecheck(studyId);
  return {
    busy: precheck.isPending,
    open() {
      if (dialogs.status === "awaiting_confirm") return dialogs.open("proposal");
      if (dialogs.status === "precheck_ok") return dialogs.open("consume");
      precheck.mutate(undefined, {
        onSuccess: (r) => {
          if (r.llm?.ok) dialogs.open("consume");
        },
      });
    },
  };
}

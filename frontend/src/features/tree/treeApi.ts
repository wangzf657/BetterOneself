import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { client, errDetail } from "@/api/client";

export function useTree(studyId: number) {
  return useQuery({
    queryKey: ["tree", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/knowledge", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
  });
}

export function useOutlineStatus(studyId: number, refetch = 4000) {
  return useQuery({
    queryKey: ["outline-status", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/outline-status", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "planning" || s === "structure_ready" ? refetch : false;
    },
  });
}

/** 树编辑统一走 mutation，成功后失效树 / 进度 / 书架（技术方案 §10）。 */
export function useInvalidateTree() {
  const qc = useQueryClient();
  return (studyId: number) => {
    void qc.invalidateQueries({ queryKey: ["tree", studyId] });
    void qc.invalidateQueries({ queryKey: ["studies"] });
    void qc.invalidateQueries({ queryKey: ["outline-status", studyId] });
    void qc.invalidateQueries({ queryKey: ["progress", studyId] });
    void qc.invalidateQueries({ queryKey: ["outline-events", studyId] });
  };
}

export function useRename(studyId: number) {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: async ({ kpId, name }: { kpId: number; name: string }) => {
      const res = await client.PATCH("/api/kps/{kp_id}", {
        params: { path: { kp_id: kpId } },
        body: { name },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: (kp) => {
      toast.success(`已重命名为「${kp.name}」`);
      invalidate(studyId);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useExclude(studyId: number) {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: async ({ kpId, reason }: { kpId: number; reason?: string | null }) => {
      const res = await client.POST("/api/kps/{kp_id}/exclude", {
        params: { path: { kp_id: kpId } },
        body: { reason: reason ?? null },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: (data) => {
      const b = data.progress_before ? `${data.progress_before.lighted} / ${data.progress_before.total}` : "—";
      const a = data.progress_after ? `${data.progress_after.lighted} / ${data.progress_after.total}` : "—";
      toast.success(`已排除「${data.kp.name}」，点亮进度 ${b} → ${a}（可恢复）`);
      invalidate(studyId);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useRestore(studyId: number) {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: async (kpId: number) => {
      const res = await client.POST("/api/kps/{kp_id}/restore", {
        params: { path: { kp_id: kpId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: (data) => {
      toast.success(`已恢复「${data.kp.name}」`);
      invalidate(studyId);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDissolve(studyId: number) {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: async (kpId: number) => {
      const res = await client.POST("/api/kps/{kp_id}/dissolve-group", {
        params: { path: { kp_id: kpId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success("已解散部分分组，章与学习数据原位保留");
      invalidate(studyId);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** 手动重试入口（B6-06）：先重新预检，结果如实落到双进度区；要不要开确认页由调用方决定。 */
export function usePrecheck(studyId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (lanes?: ("embedding" | "llm")[]) => {
      const res = await client.POST("/api/studies/{study_id}/precheck", {
        params: { path: { study_id: studyId } },
        body: lanes ? { lanes } : null,
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      for (const key of ["progress", "outline-status", "study"]) void qc.invalidateQueries({ queryKey: [key, studyId] });
      void qc.invalidateQueries({ queryKey: ["studies"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileText, Upload } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { client, errDetail, type PipelineProgress } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/basics";
import PlanConfirmDialog from "@/features/planning/PlanConfirmDialog";
import ProposalDialog from "@/features/planning/ProposalDialog";
import { LanesProgress, useProgress, type PlanDialog } from "@/features/planning/lanes";
import { usePlanningDialogs } from "@/features/planning/usePlanningDialogs";

const ACCEPT = ".pdf,.epub,.txt,.md,.markdown";

export default function NewStudyPage() {
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [useAi, setUseAi] = useState(false); // 默认不勾：不勾就是纯本地路径（B6-01）
  const [studyId, setStudyId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // 幂等键进页生成一次（P1-05）：双击/重试共用同键，后端按键去重
  const idemKeyRef = useRef(`ui-${crypto.randomUUID()}`);
  // 同步提交标志：React 状态更新前双击的第二击直接返回（BUG-003）
  const submittingRef = useRef(false);

  const create = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.set("name", name);
      fd.set("file", file!);
      fd.set("use_ai_planning", String(useAi));
      const res = await client.POST("/api/studies", {
        // openapi-fetch 的 multipart 类型由运行时 FormData 承担
        body: fd as unknown as { name: string; file: string; use_ai_planning: boolean },
        headers: { "Idempotency-Key": idemKeyRef.current },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: (study) => {
      setStudyId(study.id);
      toast.success("文件已保存，正在解析正文与目录");
    },
    onError: (e: Error) => {
      submittingRef.current = false; // 失败允许重试
      toast.error(e.message);
    },
  });

  const submit = () => {
    if (submittingRef.current || create.isPending) return;
    if (!name.trim()) return toast.error("请填写书名");
    if (!file) return toast.error("请选择主文件（EPUB / TXT / PDF / Markdown）");
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["pdf", "epub", "txt", "md", "markdown"].includes(ext))
      return toast.error(`不支持的格式 .${ext}：仅支持 EPUB、TXT、PDF、Markdown`);
    submittingRef.current = true;
    create.mutate();
  };

  const onPick = useCallback(
    (f: File | null) => {
      if (!f) return;
      setFile(f);
      if (!name) setName(f.name.replace(/\.[^.]+$/, ""));
    },
    [name],
  );

  const { data: progress } = useProgress(studyId);
  // 导入页自动弹确认：预检通过弹消耗确认，建议生成后弹树确认（B6-03/04）
  const plan = usePlanningDialogs(studyId, true);

  const viewReady = progress?.parse.status === "parsed" && studyId !== null;

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <Link to="/studies" className="mb-4 inline-flex items-center gap-1 text-sm text-ink-soft hover:text-ink">
        <ArrowLeft size={14} /> 返回我的书
      </Link>
      <h1 className="text-2xl font-bold">添加一本书</h1>
      <p className="mt-1 text-sm text-ink-soft">填个书名、选一个文件，马上就能看到技能树。</p>

      <div className="mt-6 rounded-lg border bg-white p-6">
        <Label htmlFor="book-name">书名 / 学习项目名 *</Label>
        <Input
          id="book-name"
          value={name}
          maxLength={200}
          placeholder="AI Agents in Depth"
          onChange={(e) => setName(e.target.value)}
        />

        <Label className="mt-5">主文件 *</Label>
        <div
          className="flex cursor-pointer items-center gap-3 rounded-md border border-dashed border-line p-4 hover:border-blue-400"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            onPick(e.dataTransfer.files?.[0] ?? null);
          }}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded bg-black/5">
            {file ? <FileText size={18} /> : <Upload size={18} />}
          </div>
          {file ? (
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{file.name}</div>
              <div className="text-xs text-ink-soft">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
            </div>
          ) : (
            <div className="flex-1 text-sm text-ink-soft">
              拖拽文件到这里，或点击选择；仅支持 EPUB、TXT、PDF、Markdown；每本书一个文件。
            </div>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              fileRef.current?.click();
            }}
          >
            选择文件
          </Button>
          {file && (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                setFile(null);
              }}
            >
              移除
            </Button>
          )}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
        />

        <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={useAi}
            onChange={(e) => setUseAi(e.target.checked)}
          />
          <span>
            使用 AI 规划
            <span className="block text-xs text-ink-soft">
              会调用你配置的 AI 服务并产生 token 消耗；解析完成后先给出预估，再次确认后才开始。不勾选则只做本地解析。
            </span>
          </span>
        </label>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={() => nav("/studies")}>
            取消
          </Button>
          {viewReady ? (
            <Button variant="gold" onClick={() => nav(`/studies/${studyId}`)}>
              查看技能树 →
            </Button>
          ) : (
            <Button onClick={submit} disabled={create.isPending}>
              {create.isPending ? "导入中…" : "导入并查看技能树 →"}
            </Button>
          )}
        </div>

        {studyId !== null && <ProgressSteps progress={progress} studyId={studyId} onOpenPlan={plan.open} />}
      </div>

      {studyId !== null && (
        <>
          <PlanConfirmDialog
            studyId={studyId}
            open={plan.dialog === "consume"}
            onOpenChange={(v) => {
              if (!v) plan.close("consume");
            }}
            onStarted={plan.started}
          />
          <ProposalDialog
            studyId={studyId}
            open={plan.dialog === "proposal"}
            onOpenChange={(v) => {
              if (!v) plan.close("proposal");
            }}
            onDone={() => nav(`/studies/${studyId}`)}
          />
        </>
      )}
    </div>
  );
}

function Step({ state, children }: { state: "done" | "doing" | "todo"; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span
        className={
          state === "done"
            ? "text-lighted"
            : state === "doing"
              ? "animate-pulse text-blue-600"
              : "text-ink-soft/50"
        }
      >
        {state === "done" ? "✓" : state === "doing" ? "→" : "○"}
      </span>
      <span className={state === "todo" ? "text-ink-soft/60" : ""}>{children}</span>
    </div>
  );
}

/** 重试解析 / 更换文件（仅解析失败且无学习数据时可用，B1-03）。 */
export function ParseFailActions({ studyId }: { studyId: number }) {
  const qc = useQueryClient();
  const { data: studies } = useQuery({
    queryKey: ["studies"],
    queryFn: async () => (await client.GET("/api/studies")).data ?? [],
  });
  const sourceId = studies?.find((s) => s.id === studyId)?.source_id ?? null;

  const retry = useMutation({
    mutationFn: async () => {
      if (!sourceId) throw new Error("找不到资料记录");
      const res = await client.POST("/api/sources/{source_id}/reparse", {
        params: { path: { source_id: sourceId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success("已重新开始解析");
      void qc.invalidateQueries({ queryKey: ["progress", studyId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const replace = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.set("file", file);
      const res = await client.POST("/api/studies/{study_id}/source/replace", {
        params: { path: { study_id: studyId } },
        body: fd as unknown as { name: string; file: string },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success("已更换文件，重新解析中");
      void qc.invalidateQueries({ queryKey: ["progress", studyId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="flex items-center gap-2 pt-1">
      <Button size="sm" variant="outline" onClick={() => retry.mutate()} disabled={retry.isPending || !sourceId}>
        重试解析
      </Button>
      <label className="cursor-pointer">
        <span className="inline-flex h-8 items-center rounded-md border border-line bg-white px-3 text-xs font-medium hover:bg-black/5">
          更换文件
        </span>
        <input
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) replace.mutate(f);
          }}
        />
      </label>
    </div>
  );
}

export function ProgressSteps({
  progress,
  studyId,
  onOpenPlan,
}: {
  progress?: PipelineProgress;
  studyId: number;
  onOpenPlan: (d: PlanDialog) => void;
}) {
  const p = progress;
  return (
    <div className="mt-6 space-y-2 rounded-md bg-paper p-4">
      <Step state={p ? "done" : "doing"}>文件已保存</Step>
      {p?.parse.status === "failed" ? (
        <div className="text-sm text-red-600">
          解析失败：{p.parse.error}
          <div className="mt-1.5">
            <ParseFailActions studyId={studyId} />
          </div>
        </div>
      ) : (
        <Step state={!p || p.parse.status !== "parsed" ? "doing" : "done"}>正在解析正文与目录</Step>
      )}
      {p?.parse.status === "parsed" && <LanesProgress studyId={studyId} onOpen={onOpenPlan} />}
      <p className="pt-1 text-xs text-ink-soft">你可以留在此页，也可以稍后从“我的书”回来。</p>
    </div>
  );
}

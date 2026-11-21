import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, MoreHorizontal, RotateCw } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  client,
  errDetail,
  flattenTree,
  type KnowledgeNode,
} from "@/api/client";
import { Badge, Input, Skeleton } from "@/components/ui/basics";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/menu";
import { DeleteDialog } from "@/features/studies/StudiesPage";
import { bookPref, fmtDateTime, STATUS_LABEL } from "@/lib/utils";
import ChapterPathView from "./ChapterPathView";
import DetailPanel from "./DetailPanel";
import EventsDrawer from "./EventsDrawer";
import StarMapView from "./StarMapView";
import WorkTreeView from "./WorkTreeView";
import { useOutlineStatus, useRename, useReplan, useTree } from "./treeApi";

type ViewMode = "starmap" | "worktree";

export default function TreePage() {
  const { studyId: sid } = useParams();
  const studyId = Number(sid);
  const { data: tree, isLoading, error } = useTree(studyId);
  const { data: study } = useQuery({
    queryKey: ["study", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
  });
  const outlineQ = useOutlineStatus(studyId);
  const outline = outlineQ.data;

  const hasChapter = useMemo(
    () => !!tree && flattenTree(tree.nodes).some((n) => n.is_chapter),
    [tree],
  );
  const [view, setView] = useState<ViewMode | null>(null);
  const activeView = view ?? (hasChapter ? "starmap" : "worktree"); // 无章层不虚构星盘（B2）
  const [pathChapter, setPathChapter] = useState<KnowledgeNode | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);

  const nodes = useMemo(() => (tree ? flattenTree(tree.nodes) : []), [tree]);
  const selected = nodes.find((n) => n.id === selectedId) ?? null;

  if (isLoading)
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-8 py-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  if (error || !tree)
    return (
      <div className="mx-auto max-w-3xl px-8 py-16 text-center text-sm text-ink-soft">
        加载失败：{String(error)}
      </div>
    );

  // P03-F：未识别出目录的专门空态
  if (nodes.length === 0) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-16 text-center">
        <h2 className="text-lg font-semibold">这本书没有可用的标题结构</h2>
        <p className="mt-2 text-sm text-ink-soft">
          本期不支持无目录文件的学习；手动创建学习单元在后续版本。可以重新识别，或返回更换文件。
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              const list = (await client.GET("/api/studies")).data ?? [];
              const src = list.find((s) => s.id === studyId)?.source_id;
              if (!src) return toast.error("找不到资料记录");
              const res = await client.POST("/api/sources/{source_id}/reparse", {
                params: { path: { source_id: src } },
              });
              if (res.error) toast.error(await errDetail(res));
              else toast.success("已重新开始识别");
            }}
          >
            重新识别
          </Button>
          <Button variant="ghost" asChild>
            <Link to="/studies/new">返回更换文件</Link>
          </Button>
        </div>
      </div>
    );
  }

  const progress = tree.progress;

  return (
    <div className="mx-auto max-w-6xl px-8 py-6">
      {/* 页头 */}
      <Link to="/studies" className="mb-2 inline-flex items-center gap-1 text-sm text-ink-soft hover:text-ink">
        <ArrowLeft size={14} /> 我的书
      </Link>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-bold">{study?.name}</h1>
          {outline?.thesis && (
            <p className="mt-1 line-clamp-2 text-sm text-ink-soft" title={outline.thesis}>
              全书总述：{outline.thesis}
            </p>
          )}
        </div>
        <div className="flex items-baseline gap-1">
          {progress ? (
            <>
              <span className="text-4xl font-bold text-lighted">●</span>
              <span className="text-3xl font-bold">
                {" "}
                {progress.lighted} / {progress.total}
              </span>
              <span className="ml-1 text-sm text-ink-soft">已点亮</span>
            </>
          ) : (
            <span className="text-sm text-ink-soft">—（无有效学习单元）</span>
          )}
        </div>
        <CaliberBadge />
        <BookMenu studyId={studyId} name={study?.name ?? ""} onRename={() => setRenameOpen(true)} />
      </div>

      {/* 继续上次 */}
      <ContinueRow studyId={studyId} nodes={nodes} />

      {/* 状态条 */}
      <StatusBar studyId={studyId} />

      {/* 工具栏 */}
      <div className="mt-4 mb-4 flex items-center justify-between">
        {pathChapter ? (
          <button
            className="flex items-center gap-1 text-sm text-ink-soft hover:text-ink"
            onClick={() => setPathChapter(null)}
          >
            <ArrowLeft size={14} /> 返回星盘
          </button>
        ) : (
          <span className="text-sm text-ink-soft">
            {activeView === "starmap" ? "章节星盘 · 进度与导航" : "工作树 · 整理操作"}
          </span>
        )}
        {hasChapter && !pathChapter && (
          <div className="flex rounded-md border bg-white p-0.5 text-sm">
            <button
              className={`rounded px-3 py-1 ${activeView === "starmap" ? "bg-ink text-white" : "text-ink-soft"}`}
              onClick={() => {
                setView("starmap");
                bookPref(studyId, "view", "starmap", "starmap");
              }}
            >
              星盘
            </button>
            <button
              className={`rounded px-3 py-1 ${activeView === "worktree" ? "bg-ink text-white" : "text-ink-soft"}`}
              onClick={() => {
                setView("worktree");
                bookPref(studyId, "view", "starmap", "worktree");
              }}
            >
              工作树
            </button>
          </div>
        )}
        <button
          className="ml-2 text-sm text-ink-soft underline-offset-2 hover:underline"
          onClick={() => setEventsOpen(true)}
        >
          结构与规划记录
        </button>
      </div>

      {/* 主工作区 */}
      {pathChapter ? (
        <ChapterPathView
          studyId={studyId}
          chapter={pathChapter}
          onSelect={setSelectedId}
          selectedId={selectedId}
          onBackToMap={() => setPathChapter(null)}
          onEnterChapter={setPathChapter}
          nodes={nodes}
        />
      ) : activeView === "starmap" && hasChapter ? (
        <StarMapView tree={tree} onSelect={setSelectedId} onEnterChapter={setPathChapter} />
      ) : (
        <WorkTreeView
          studyId={studyId}
          tree={tree}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      )}

      {/* 详情面板 */}
      {selected && (
        <DetailPanel
          key={selected.id}
          studyId={studyId}
          node={selected}
          onClose={() => setSelectedId(null)}
        />
      )}

      <EventsDrawer studyId={studyId} open={eventsOpen} onOpenChange={setEventsOpen} />
      <RenameBookDialog
        studyId={studyId}
        open={renameOpen}
        onOpenChange={setRenameOpen}
        initial={study?.name ?? ""}
      />
    </div>
  );
}

function CaliberBadge() {
  const [open, setOpen] = useState(false);
  return (
    <button
      className="rounded border px-2 py-1 text-xs text-ink-soft hover:bg-black/5"
      onClick={() => setOpen((v) => !v)}
      onBlur={() => setOpen(false)}
    >
      口径 ?
      {open && (
        <span className="absolute z-30 mt-2 w-72 rounded-md border bg-white p-3 text-left text-xs leading-relaxed text-ink-soft shadow-lg">
          点亮 = 节点测验当前通过，不含长期记忆验证；已排除节点不计入；复习体系在后续版本加入。
        </span>
      )}
    </button>
  );
}

function ContinueRow({ studyId, nodes }: { studyId: number; nodes: KnowledgeNode[] }) {
  const nav = useNavigate();
  const { data: studies } = useQuery({
    queryKey: ["studies"],
    queryFn: async () => (await client.GET("/api/studies")).data ?? [],
  });
  const study = studies?.find((s) => s.id === studyId);
  const lastKp = study?.last_kp;
  const fallback =
    nodes.find((n) => n.is_learning_unit && n.status === "unlearned") ??
    nodes.find((n) => n.is_learning_unit) ??
    null;
  const target = lastKp?.id ?? fallback?.id ?? null;
  const label = lastKp
    ? `继续上次：${lastKp.name}（${STATUS_LABEL[lastKp.status ?? "unlearned"]}）`
    : fallback
      ? `从「${fallback.name}」开始`
      : "暂无可学习单元";
  return (
    <div className="mt-3 flex items-center justify-between">
      <span className="text-sm text-ink-soft">{label}</span>
      <Button size="sm" disabled={!target} onClick={() => target && nav(`/studies/${studyId}/learn/${target}`)}>
        继续学习 →
      </Button>
    </div>
  );
}

function StatusBar({ studyId }: { studyId: number }) {
  const outlineQuery = useOutlineStatus(studyId);
  const outline = outlineQuery.data;
  const { data: progress } = useQuery({
    queryKey: ["progress", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/progress", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    refetchInterval: (q) =>
      q.state.data && (q.state.data.parse.status === "parsing" || q.state.data.parse.status === "pending")
        ? 2000
        : false,
  });
  const replan = useReplan(studyId);
  if (!outline) return null;
  const s = outline.status;
  const thesisReady = s === "ready";

  let content: React.ReactNode = null;
  if (progress && ["pending", "parsing"].includes(progress.parse.status)) {
    content = <span>正在读取原书目录…</span>;
  } else if (progress && progress.parse.status === "parsed" && s === "structure_ready") {
    content = <span>原目录已可查看，正在准备可回跳的原文；AI 调整等引用就绪后应用</span>;
  } else if (s === "planning") {
    content = <span className="animate-pulse">正在按书的逻辑拟大纲，原目录仍可编辑</span>;
  } else if (s === "skipped") {
    content = (
      <span>
        未配置 AI，已保留原书目录；可手动排除，或
        <button className="mx-1 underline" onClick={() => undefined} disabled>
          稍后配置重试
        </button>
        （到设置页配置）
      </span>
    );
  } else if (s === "failed") {
    content = (
      <span>
        拟大纲未完成（仅规划失败，不影响讲解与测验），原目录未受影响。{outline.error}
        <Button size="sm" variant="outline" className="ml-2" onClick={() => replan.mutate()} disabled={replan.isPending}>
          <RotateCw size={13} /> 稍后重试
        </Button>
      </span>
    );
  } else if (thesisReady) {
    const a = outline.adjust_summary;
    content = (
      <span className="flex flex-wrap items-center gap-2">
        <Badge tone="purple">AI 拟大纲</Badge>
        已拟大纲：{a ? `${a.parts} 个部分、排除 ${a.excluded} 项、拆分 ${a.split} 处、合并 ${a.merged} 处（实际应用 ${a.applied} 项${a.skipped ? `、跳过 ${a.skipped} 项` : ""}）` : "完成"}
        <button className="text-blue-600 hover:underline" onClick={() => undefined} />
      </span>
    );
  } else if ((outline.low_confidence_count ?? 0) > 0) {
    content = <span>部分层级由标题样式推断（低置信节点 {outline.low_confidence_count} 个），请检查标记节点</span>;
  }
  if (!content) return null;
  return (
    <div className="mt-3 rounded-md border bg-white px-4 py-2.5 text-sm text-ink-soft">{content}</div>
  );
}

function BookMenu({
  studyId,
  name,
  onRename,
}: {
  studyId: number;
  name: string;
  onRename: () => void;
}) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger className="rounded p-1.5 text-ink-soft hover:bg-black/5">
          <MoreHorizontal size={16} />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={onRename}>重命名书</DropdownMenuItem>
          <DropdownMenuItem
            className="text-red-600"
            onSelect={(e) => {
              e.preventDefault();
              setDeleteOpen(true);
            }}
          >
            删除（影响清单）
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DeleteDialog studyId={studyId} name={name} open={deleteOpen} onOpenChange={setDeleteOpen} />
    </>
  );
}

function RenameBookDialog({
  studyId,
  open,
  onOpenChange,
  initial,
}: {
  studyId: number;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initial: string;
}) {
  const qc = useQueryClient();
  const rename = useRename(studyId);
  const [name, setName] = useState(initial);
  const mutate = useMutation({
    mutationFn: async (value: string) => {
      const res = await client.PATCH("/api/studies/{study_id}", {
        params: { path: { study_id: studyId } },
        body: { name: value },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success("已重命名");
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["study", studyId] });
      void qc.invalidateQueries({ queryKey: ["studies"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  void rename;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader title="重命名书" />
        <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
        <div className="mt-4 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button disabled={!name.trim() || mutate.isPending} onClick={() => mutate.mutate(name.trim())}>
            保存
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function NodeStatusDot({ status }: { status?: string | null }) {
  if (!status) return null;
  if (status === "lighted") return <span className="text-lighted">●</span>;
  if (status === "learning") return <span className="text-blue-500">◐</span>;
  return <span className="text-unlearned">○</span>;
}

export function nextChapterOf(nodes: KnowledgeNode[], chapterId: number): KnowledgeNode | null {
  const chapters = nodes.filter((n) => n.is_chapter);
  const idx = chapters.findIndex((c) => c.id === chapterId);
  return idx >= 0 && idx + 1 < chapters.length ? chapters[idx + 1] : null;
}

export { fmtDateTime, ChevronRight };

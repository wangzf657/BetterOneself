import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { client, errDetail, type DeleteImpact, type StudyItem } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/basics";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogClose,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/menu";
import { Input } from "@/components/ui/basics";
import { ParseFailActions } from "./NewStudyPage";
import { fmtDate } from "@/lib/utils";

export default function StudiesPage() {
  const { data: studies, isLoading } = useQuery({
    queryKey: ["studies"],
    queryFn: async () => {
      const res = await client.GET("/api/studies");
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
  });

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">我的书</h1>
        <Button onClick={() => undefined} asChild>
          <Link to="/studies/new">
            <Plus size={16} /> 添加一本书
          </Link>
        </Button>
      </div>

      {isLoading && <div className="text-sm text-ink-soft">正在加载…</div>}

      {studies && studies.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <BookOpen className="mx-auto mb-3 text-ink-soft/50" size={36} />
          <p className="font-medium">还没有书</p>
          <p className="mt-1 text-sm text-ink-soft">
            从一本书开始，看到技能树，点亮第一个节点。
          </p>
          <Button className="mt-4" asChild>
            <Link to="/studies/new">
              <Plus size={16} /> 添加一本书
            </Link>
          </Button>
        </div>
      )}

      <div className="space-y-3">
        {studies?.map((s) => <StudyCard key={s.id} study={s} />)}
      </div>
    </div>
  );
}

function StudyCard({ study }: { study: StudyItem }) {
  const nav = useNavigate();
  return (
    <div className="flex items-center gap-4 rounded-lg border bg-white p-5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold">{study.name}</span>
          {study.source_type && <Badge>{study.source_type.toUpperCase()}</Badge>}
          {study.parse_status === "failed" && <Badge tone="amber">解析失败</Badge>}
        </div>
        <div className="mt-1 flex items-center gap-3 text-sm text-ink-soft">
          {study.progress ? (
            <span className="text-lighted">● {study.progress.lighted} / {study.progress.total} 已点亮</span>
          ) : (
            <span>—（无有效学习单元）</span>
          )}
          {study.last_kp && (
            <span className="truncate">
              上次：{study.last_kp.name}（{study.last_kp.status === "lighted" ? "已点亮" : study.last_kp.status === "learning" ? "学习中" : "未学"}）
            </span>
          )}
          {study.last_learned_at && <span>{fmtDate(study.last_learned_at)}</span>}
        </div>
        {study.parse_status === "failed" && study.parse_error && (
          <div className="mt-2 text-sm text-red-600">
            {study.parse_error}
            <div className="mt-1.5">
              <ParseFailActions studyId={study.id} />
            </div>
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          size="sm"
          onClick={() => {
            // 继续学习：回到上次节点；没有历史则进树的第一个未点亮学习单元
            if (study.last_kp) nav(`/studies/${study.id}/learn/${study.last_kp.id}`);
            else nav(`/studies/${study.id}`);
          }}
        >
          继续学习
        </Button>
        <Button size="sm" variant="outline" asChild>
          <Link to={`/studies/${study.id}`}>查看技能树</Link>
        </Button>
        <CardMenu studyId={study.id} name={study.name} />
      </div>
    </div>
  );
}

function CardMenu({ studyId, name }: { studyId: number; name: string }) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger className="rounded p-1.5 text-ink-soft hover:bg-black/5">···</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem
            className="text-red-600"
            onSelect={(e) => {
              e.preventDefault();
              setDeleteOpen(true);
            }}
          >
            删除这本书
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DeleteDialog studyId={studyId} name={name} open={deleteOpen} onOpenChange={setDeleteOpen} />
    </>
  );
}

export function DeleteDialog({
  studyId,
  name,
  open,
  onOpenChange,
}: {
  studyId: number;
  name: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [confirmName, setConfirmName] = useState("");
  const { data: impact } = useQuery<DeleteImpact>({
    queryKey: ["delete-impact", studyId],
    queryFn: async () => {
      const res = await client.GET("/api/studies/{study_id}/delete-impact", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: open,
  });
  const del = useMutation({
    mutationFn: async () => {
      const res = await client.DELETE("/api/studies/{study_id}", {
        params: { path: { study_id: studyId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      toast.success(`已删除《${name}》`);
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["studies"] });
      nav("/studies");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title={`删除《${name}》？`}
          desc="以下内容将被一并删除，且无法恢复："
        />
        <ul className="space-y-1 text-sm text-ink-soft">
          <li>· 学习会话 {impact?.sessions ?? "…"} 个</li>
          <li>· 测验记录 {impact?.quizzes ?? "…"} 组</li>
          <li>· 已点亮节点 {impact?.lighted ?? "…"} 个</li>
          <li>· 节点笔记 {impact?.notes ?? "…"} 篇</li>
        </ul>
        <p className="mt-4 text-sm">输入书名 <b>{name}</b> 确认删除：</p>
        <Input className="mt-2" value={confirmName} onChange={(e) => setConfirmName(e.target.value)} />
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button
            variant="danger"
            disabled={confirmName !== name || del.isPending}
            onClick={() => del.mutate()}
          >
            {del.isPending ? "删除中…" : "确认删除"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function CardMenuSeparator() {
  return <DropdownMenuSeparator />;
}

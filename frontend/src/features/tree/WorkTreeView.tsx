import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";
import type { KnowledgeNode, KnowledgeTree } from "@/api/client";
import { Badge, Input } from "@/components/ui/basics";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/menu";
import { cn } from "@/lib/utils";
import { NodeStatusDot } from "./TreePage";
import { useDissolve, useExclude, useRename, useRestore } from "./treeApi";

/** 工作树（P03-C 操作台）：搜索、展开/折叠、筛选、重命名、排除/恢复、解散分组。 */
export default function WorkTreeView({
  tree,
  selectedId,
  onSelect,
  studyId,
}: {
  tree: KnowledgeTree;
  selectedId: number | null;
  onSelect: (id: number) => void;
  studyId: number;
}) {
  const [query, setQuery] = useState("");
  const [showExcluded, setShowExcluded] = useState<"all" | "excluded">("all");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const matches = useMemo(() => {
    if (!query.trim()) return null;
    const q = query.trim().toLowerCase();
    const hits = new Set<number>();
    const walk = (n: KnowledgeNode) => {
      if (n.name.toLowerCase().includes(q)) {
        hits.add(n.id);
        let p: number | null | undefined = n.parent_id;
        while (p != null) {
          hits.add(p);
          p = tree.nodes.find((x) => x.id === p)?.parent_id ?? null;
        }
      }
      for (const c of n.children ?? []) walk(c);
    };
    for (const root of tree.nodes) walk(root);
    return hits;
  }, [query, tree.nodes]);

  return (
    <div className="rounded-lg border bg-white">
      <div className="flex items-center gap-2 border-b px-4 py-2.5">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2.5 top-2.5 text-ink-soft" />
          <Input
            className="pl-8"
            placeholder="搜索目录…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button
          className="text-xs text-ink-soft hover:text-ink"
          onClick={() => setCollapsed(new Set())}
        >
          展开全部
        </button>
        <button
          className="text-xs text-ink-soft hover:text-ink"
          onClick={() => {
            const ids = new Set<number>();
            const walk = (n: KnowledgeNode) => {
              if (n.children?.length) ids.add(n.id);
              for (const c of n.children ?? []) walk(c);
            };
            for (const r of tree.nodes) walk(r);
            setCollapsed(ids);
          }}
        >
          折叠到章
        </button>
        <select
          className="h-8 rounded border bg-white px-2 text-xs"
          value={showExcluded}
          onChange={(e) => setShowExcluded(e.target.value as "all" | "excluded")}
        >
          <option value="all">全部</option>
          <option value="excluded">已排除</option>
        </select>
      </div>
      <div className="p-2">
        {tree.nodes.map((root) => (
          <Row
            key={root.id}
            studyId={studyId}
            node={root}
            depth={0}
            selectedId={selectedId}
            onSelect={onSelect}
            collapsed={collapsed}
            setCollapsed={setCollapsed}
            matches={matches}
            showExcluded={showExcluded}
          />
        ))}
      </div>
    </div>
  );
}

function originBadge(n: KnowledgeNode) {
  if (n.origin === "ai_group") return <Badge tone="purple">AI 分组</Badge>;
  if (n.origin.startsWith("ai_")) return <Badge tone="purple">AI 调整</Badge>;
  if (n.origin === "toc") return null;
  return null;
}

function Row({
  studyId,
  node,
  depth,
  selectedId,
  onSelect,
  collapsed,
  setCollapsed,
  matches,
  showExcluded,
}: {
  studyId: number;
  node: KnowledgeNode;
  depth: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
  collapsed: Set<number>;
  setCollapsed: (s: Set<number>) => void;
  matches: Set<number> | null;
  showExcluded: "all" | "excluded";
}) {
  const children = node.children ?? [];
  const isOpen = matches ? children.some((c) => matches.has(c.id)) : !collapsed.has(node.id);
  if (matches && !matches.has(node.id)) return null;
  const effectivelyExcluded = node.excluded;
  if (showExcluded === "excluded" && !effectivelyExcluded) {
    // 只保留已排除节点（及其祖先路径）
    const hasExcludedDescendant = (n: KnowledgeNode): boolean =>
      n.excluded || (n.children ?? []).some(hasExcludedDescendant);
    if (!hasExcludedDescendant(node)) return null;
  }

  return (
    <div>
      <div
        className={cn(
          "group flex h-9 cursor-pointer items-center gap-1.5 rounded pr-2 text-sm hover:bg-black/5",
          selectedId === node.id && "bg-blue-50",
        )}
        style={{ paddingLeft: depth * 20 + 6 }}
        onClick={() => onSelect(node.id)}
      >
        {children.length ? (
          <button
            className="text-ink-soft"
            onClick={(e) => {
              e.stopPropagation();
              const next = new Set(collapsed);
              if (next.has(node.id)) next.delete(node.id);
              else next.add(node.id);
              setCollapsed(next);
            }}
          >
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <span className="w-[14px]" />
        )}
        {node.is_learning_unit && <NodeStatusDot status={node.status} />}
        <span
          className={cn(
            "max-w-[46%] truncate",
            effectivelyExcluded && "text-ink-soft line-through",
          )}
          title={node.name}
        >
          {node.name}
        </span>
        {originBadge(node)}
        {node.confidence < 0.6 && <span className="text-amber-500" title="低置信度">●</span>}
        {children.length > 0 && !effectivelyExcluded && (
          <span className="text-xs text-ink-soft">
            {node.lighted_count ?? 0} / {node.valid_total ?? 0}
          </span>
        )}
        {effectivelyExcluded && <Badge tone="muted">已排除</Badge>}
        {node.is_learning_unit && node.status === "learning" && <Badge tone="blue">学习中</Badge>}
        <div className="ml-auto opacity-0 group-hover:opacity-100">
          <NodeMenu studyId={studyId} node={node} />
        </div>
      </div>
      {isOpen &&
        children.map((c) => (
          <Row
            key={c.id}
            studyId={studyId}
            node={c}
            depth={depth + 1}
            selectedId={selectedId}
            onSelect={onSelect}
            collapsed={collapsed}
            setCollapsed={setCollapsed}
            matches={matches}
            showExcluded={showExcluded}
          />
        ))}
    </div>
  );
}

function NodeMenu({ studyId, node }: { studyId: number; node: KnowledgeNode }) {
  const rename = useRename(studyId);
  const exclude = useExclude(studyId);
  const restore = useRestore(studyId);
  const dissolve = useDissolve(studyId);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="rounded px-1.5 text-ink-soft hover:bg-black/10"
        onClick={(e) => e.stopPropagation()}
      >
        ···
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <RenameItem onRename={(name) => rename.mutate({ kpId: node.id, name })} initial={node.name} />
        {node.excluded ? (
          <DropdownMenuItem onSelect={() => restore.mutate(node.id)}>恢复节点</DropdownMenuItem>
        ) : (
          <ExcludeItem
            kpId={node.id}
            kpName={node.name}
            onExclude={(reason) => exclude.mutate({ kpId: node.id, reason })}
          />
        )}
        {node.origin === "ai_group" && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-violet-700" onSelect={() => dissolve.mutate(node.id)}>
              解散部分分组
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

import { Dialog, DialogClose, DialogContent, DialogHeader } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";
import { client, errDetail, type ExcludeImpact } from "@/api/client";

function RenameItem({ initial, onRename }: { initial: string; onRename: (name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(initial);
  return (
    <>
      <DropdownMenuItem
        onSelect={(e) => {
          e.preventDefault();
          setName(initial);
          setOpen(true);
        }}
      >
        重命名
      </DropdownMenuItem>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader title="重命名节点" desc={`原名称：${initial}`} />
          <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          <div className="mt-4 flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">取消</Button>
            </DialogClose>
            <Button
              disabled={!name.trim()}
              onClick={() => {
                onRename(name.trim());
                setOpen(false);
              }}
            >
              保存
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ExcludeItem({
  kpId,
  kpName,
  onExclude,
}: {
  kpId: number;
  kpName: string;
  onExclude: (reason?: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const { data: impact } = useQuery<ExcludeImpact>({
    queryKey: ["exclude-impact", kpId],
    queryFn: async () => {
      const res = await client.GET("/api/kps/{kp_id}/exclude-impact", {
        params: { path: { kp_id: kpId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    enabled: open,
  });
  const fmt = (p: ExcludeImpact["progress_before"]) =>
    p ? `${p.lighted} / ${p.total}` : "—（无有效学习单元）";
  return (
    <>
      <DropdownItemShim
        onSelect={() => {
          setReason("");
          setOpen(true);
        }}
      >
        排除节点
      </DropdownItemShim>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader title={`排除「${kpName}」？`} />
          <ul className="space-y-1.5 text-sm text-ink-soft">
            <li>· 该节点与子节点退出学习范围；</li>
            <li>
              · 点亮进度将从{" "}
              <b className="text-ink">{fmt(impact?.progress_before)}</b> 变为{" "}
              <b className="text-ink">{fmt(impact?.progress_after)}</b>
              {impact?.lighted_affected ? `（含已点亮 ${impact.lighted_affected} 个）` : ""}；
            </li>
            <li>· 已有会话与测验记录保留，可随时恢复。</li>
          </ul>
          <Input
            className="mt-3"
            placeholder="排除原因（可选）"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="mt-4 flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">取消</Button>
            </DialogClose>
            <Button
              onClick={() => {
                onExclude(reason.trim() || undefined);
                setOpen(false);
              }}
            >
              确认排除
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DropdownItemShim({ children, onSelect }: { children: React.ReactNode; onSelect: () => void }) {
  return (
    <DropdownMenuItem
      onSelect={(e) => {
        e.preventDefault();
        onSelect();
      }}
    >
      {children}
    </DropdownMenuItem>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Send, Square } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  client,
  errDetail,
  postSSE,
  renderMarkdown,
  type MessageItem,
  type SessionDetail,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/basics";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/menu";
import { SCHEMES, STATUS_LABEL, bookPref, cn } from "@/lib/utils";
import NotePane, { insertQuoteAtCursor, useDebouncedSave } from "./NotePane";
import QuizCard, { type QuizView } from "./QuizCard";
import SourcePane from "./SourcePane";

export default function LearnPage() {
  const { studyId: sid, nodeId: nid } = useParams();
  const studyId = Number(sid);
  const nodeId = Number(nid);
  const nav = useNavigate();
  const qc = useQueryClient();

  const { data: detail, isLoading, error } = useQuery<SessionDetail>({
    queryKey: ["session", studyId, nodeId],
    queryFn: async () => {
      const res = await client.POST("/api/studies/{study_id}/sessions", {
        params: { path: { study_id: studyId } },
        body: { kp_id: nodeId },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    retry: false,
  });

  const sessionId = detail?.session.id ?? null;
  const excluded = detail?.session.excluded ?? false;

  const { data: content } = useQuery({
    queryKey: ["kp-content", nodeId],
    queryFn: async () => {
      const res = await client.GET("/api/kps/{kp_id}/content", {
        params: { path: { kp_id: nodeId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
  });

  const { data: note } = useQuery({
    queryKey: ["note", nodeId],
    queryFn: async () => {
      const res = await client.GET("/api/kps/{kp_id}/note", {
        params: { path: { kp_id: nodeId } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
  });

  // ---- 布局（折叠按书记忆；<1024 三页签）----
  const [srcCollapsed, setSrcCollapsed] = useState(() => bookPref(studyId, "srcCollapsed", false));
  const [noteCollapsed, setNoteCollapsed] = useState(() => bookPref(studyId, "noteCollapsed", false));
  const [highlightChunk, setHighlightChunk] = useState<number | null>(null);
  const [tab, setTab] = useState<"source" | "chat" | "note">("chat");
  const [narrow, setNarrow] = useState(() => window.innerWidth < 1024);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const fn = () => setNarrow(mq.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  const goSource = useCallback(
    (chunkId: number) => {
      setSrcCollapsed(false);
      bookPref(studyId, "srcCollapsed", false, false);
      setTab("source");
      setHighlightChunk(chunkId);
      setTimeout(() => {
        document.getElementById(`chunk-${chunkId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
        setTimeout(() => setHighlightChunk(null), 2400);
      }, 60);
    },
    [studyId],
  );

  // ---- SSE 生成（开场 / 对话共用状态）----
  const [streaming, setStreaming] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const openedOnce = useRef(false);

  const hasAssistant = !!detail?.messages.some((m) => m.role === "assistant");

  const runSSE = useCallback(
    async (path: "opening" | "chat", body: Record<string, unknown>) => {
      if (!sessionId) return;
      setStreaming("");
      setStreamError(null);
      const ac = new AbortController();
      abortRef.current = ac;
      await postSSE(
        `/api/sessions/${sessionId}/${path}`,
        body,
        {
          onDelta: (t) => setStreaming((s) => (s ?? "") + t),
          onDone: () => {
            setStreaming(null);
            void qc.invalidateQueries({ queryKey: ["session", studyId, nodeId] });
            void qc.invalidateQueries({ queryKey: ["studies"] });
          },
          onError: (e) => {
            setStreaming(null);
            setStreamError(e.detail);
          },
        },
        ac.signal,
      ).catch(() => setStreaming((s) => (ac.signal.aborted ? s : s)));
    },
    [sessionId, qc, studyId, nodeId],
  );

  // 开场：进会话若无 assistant 消息自动生成（B3-01；失败不伪造用户消息）
  useEffect(() => {
    if (!sessionId || isLoading || hasAssistant || openedOnce.current || excluded) return;
    openedOnce.current = true;
    void runSSE("opening", {});
  }, [sessionId, isLoading, hasAssistant, excluded, runSSE]);

  const [input, setInput] = useState("");
  const sendChat = async (preset?: string) => {
    const text = (preset ?? input).trim();
    if (!text || streaming !== null) return;
    setInput("");
    await runSSE("chat", { content: text });
  };

  const stopStream = () => {
    abortRef.current?.abort();
    setStreaming(null);
    void qc.invalidateQueries({ queryKey: ["session", studyId, nodeId] });
  };

  // ---- 测验 ----
  const genQuiz = useMutation({
    mutationFn: async () => {
      const res = await client.POST("/api/sessions/{session_id}/quizzes", {
        params: { path: { session_id: sessionId! } },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["session", studyId, nodeId] });
      toast.success("测验已生成：先看说明里的通过线，再作答");
      setTimeout(() => {
        document
          .querySelectorAll("[data-quiz]")
          .item(document.querySelectorAll("[data-quiz]").length - 1)
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 150);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // ---- 笔记自动保存（三态）----
  const [noteText, setNoteText] = useState("");
  useEffect(() => {
    if (note) setNoteText(note.content_md);
  }, [note]);
  const noteRef = useRef<HTMLTextAreaElement | null>(null);
  const saveNote = useCallback(
    (v: string) =>
      client
        .PUT("/api/kps/{kp_id}/note", { params: { path: { kp_id: nodeId } }, body: { content_md: v } })
        .then((res) => {
          if (res.error) throw new Error("save failed");
        }),
    [nodeId],
  );
  const [noteState, noteSavedAt] = useDebouncedSave(noteText, saveNote);
  useEffect(() => {
    if (noteState !== "failed") return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [noteState]);

  const quoteToNote = (text: string, chunkId: number) => {
    const title = content?.chunks.find((c) => c.id === chunkId)?.title ?? "原文";
    setNoteCollapsed(false);
    bookPref(studyId, "noteCollapsed", false, false);
    setNoteText((v) => (v ? `${v}\n` : "") + insertQuoteAtCursor(noteRef.current, text, chunkId, title));
    setTab("note");
  };

  const askAbout = (text: string) => {
    void sendChat(`请就这段原文讲讲：\n「${text}」`);
  };

  // ---- 学习方法 ----
  const scheme = detail?.session.scheme ?? "guided";
  const patchScheme = useMutation({
    mutationFn: async (s: string) => {
      const res = await client.PATCH("/api/sessions/{session_id}/scheme", {
        params: { path: { session_id: sessionId! } },
        body: { scheme: s as "guided" | "lecture" | "drill" },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data;
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["session", studyId, nodeId] }),
    onError: (e: Error) => toast.error(e.message),
  });

  // 对话流：messages + quizzes 按时间合并（数据模型 §3.9）
  const timeline = useMemo(() => {
    type Item =
      | { kind: "msg"; at: string; msg: MessageItem }
      | { kind: "quiz"; at: string; quiz: QuizView };
    const items: Item[] = [];
    for (const m of detail?.messages ?? [])
      items.push({ kind: "msg", at: m.created_at as unknown as string, msg: m });
    for (const q of (detail?.quizzes ?? []) as unknown as QuizView[])
      items.push({
        kind: "quiz",
        at: ((q.created_at ?? q.answered_at ?? "") as string),
        quiz: q,
      });
    items.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
    return items;
  }, [detail]);

  const nodeStatus = useMemo(() => {
    const quizzes = (detail?.quizzes ?? []) as unknown as QuizView[];
    if (quizzes.some((q) => q.passed)) return "lighted";
    if ((detail?.messages.length ?? 0) > 0 || quizzes.length > 0) return "learning";
    return "unlearned";
  }, [detail]);

  const [guideOpen, setGuideOpen] = useState(() => localStorage.getItem("bo.guide.dismissed") !== "1");

  if (isLoading)
    return (
      <div className="flex h-screen items-center justify-center">
        <Skeleton className="h-8 w-48" />
      </div>
    );
  if (error || !detail)
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 text-sm text-ink-soft">
        无法进入学习：该节点当前不能学习（可能已排除或原文引用未就绪）。
        <Button variant="outline" onClick={() => nav(`/studies/${studyId}`)}>
          返回技能树
        </Button>
      </div>
    );

  const kpPath = detail.session.kp_path ?? [];
  const quizzes = (detail.quizzes ?? []) as unknown as QuizView[];
  const hasOpenQuiz = quizzes.some((q) => !q.answered_at);

  const chatColumn = (
    <ChatColumn
      excluded={excluded}
      guideOpen={guideOpen}
      onDismissGuide={() => {
        localStorage.setItem("bo.guide.dismissed", "1");
        setGuideOpen(false);
      }}
      timeline={timeline}
      streaming={streaming}
      streamError={streamError}
      onCite={goSource}
      onRetry={() => (hasAssistant ? sendChat() : runSSE("opening", {}))}
      onRetake={() => genQuiz.mutate()}
      studyId={studyId}
    />
  );
  const chatInput = (
    <ChatInput
      value={input}
      onChange={setInput}
      onSend={() => sendChat()}
      onStop={stopStream}
      streaming={streaming !== null}
      excluded={excluded}
      generatingQuiz={genQuiz.isPending}
      onQuiz={() => genQuiz.mutate()}
    />
  );
  const sourcePane = (
    <SourcePane
      content={content}
      highlightChunkId={highlightChunk}
      onCite={goSource}
      onAskAbout={askAbout}
      onQuoteToNote={quoteToNote}
      collapsed={srcCollapsed && !narrow}
      onToggle={() => {
        const v = !srcCollapsed;
        setSrcCollapsed(v);
        bookPref(studyId, "srcCollapsed", false, v);
        if (!v) setTab("source");
      }}
    />
  );
  const notePane = (
    <NotePane
      kpPath={kpPath}
      initial={noteText}
      saveState={noteState}
      savedAt={noteSavedAt}
      onChange={setNoteText}
      onGoSource={goSource}
      collapsed={noteCollapsed && !narrow}
      onToggle={() => {
        const v = !noteCollapsed;
        setNoteCollapsed(v);
        bookPref(studyId, "noteCollapsed", false, v);
        if (!v) setTab("note");
      }}
      textareaRef={noteRef}
    />
  );

  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b bg-white px-4">
        <button
          className="flex items-center gap-1 text-sm text-ink-soft hover:text-ink"
          onClick={() => nav(`/studies/${studyId}`)}
        >
          <ArrowLeft size={14} /> 返回技能树
        </button>
        <span className="truncate text-sm font-medium">
          {kpPath.slice(-2).join(" / ") || detail.session.kp_name}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Select value={scheme} onValueChange={(v) => patchScheme.mutate(v)}>
            <SelectTrigger className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCHEMES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <NodeCaliber status={nodeStatus} hasOpenQuiz={hasOpenQuiz} />
        </div>
      </header>

      {narrow ? (
        <>
          <div className="flex shrink-0 border-b bg-white text-sm">
            {(["source", "chat", "note"] as const).map((t) => (
              <button
                key={t}
                className={cn("flex-1 py-2", tab === t ? "border-b-2 border-ink font-medium" : "text-ink-soft")}
                onClick={() => setTab(t)}
              >
                {t === "source" ? "原文" : t === "chat" ? "陪学" : "笔记"}
              </button>
            ))}
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto">
              {tab === "source" && sourcePane}
              {tab === "chat" && <div className="h-full">{chatColumn}</div>}
              {tab === "note" && notePane}
            </div>
            {tab === "chat" && <div className="border-t">{chatInput}</div>}
          </div>
        </>
      ) : (
        <div className="flex min-h-0 flex-1">
          {sourcePane}
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto">{chatColumn}</div>
            <div className="border-t">{chatInput}</div>
          </div>
          {notePane}
        </div>
      )}
    </div>
  );
}

function NodeCaliber({ status, hasOpenQuiz }: { status: string; hasOpenQuiz: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        className="rounded border px-2 py-1 text-xs text-ink-soft hover:bg-black/5"
        onClick={() => setOpen((v) => !v)}
      >
        节点状态与口径 ▾
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-50 w-64 rounded-md border bg-white p-3 text-left text-xs leading-relaxed text-ink-soft shadow-lg">
          节点状态：{STATUS_LABEL[status]}
          {hasOpenQuiz && "；有一组测验进行中"}
          ；点亮 = 节点测验当前通过，不含长期记忆验证；提问与阅读不改变状态。
        </div>
      )}
    </div>
  );
}

interface TimelineItem {
  kind: "msg" | "quiz";
  at: string;
  msg?: MessageItem;
  quiz?: QuizView;
}

function ChatColumn({
  excluded,
  guideOpen,
  onDismissGuide,
  timeline,
  streaming,
  streamError,
  onCite,
  onRetry,
  onRetake,
  studyId,
}: {
  excluded: boolean;
  guideOpen: boolean;
  onDismissGuide: () => void;
  timeline: TimelineItem[];
  streaming: string | null;
  streamError: string | null;
  onCite: (chunkId: number) => void;
  onRetry: () => void;
  onRetake: () => void;
  studyId: number;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [timeline.length, streaming]);
  return (
    <div className="bg-paper">
      <div className="mx-auto max-w-3xl space-y-4 px-6 py-5">
        {guideOpen && !excluded && (
          <div className="flex items-center justify-between rounded-md border border-dashed bg-white px-4 py-2 text-xs text-ink-soft">
            读原文 → 问不懂 → 考一组
            <button className="hover:text-ink" onClick={onDismissGuide}>
              知道了 ×
            </button>
          </div>
        )}
        {excluded && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            该节点已排除：历史会话与测验只读可回看，不能开始新的学习或正式测验。
          </div>
        )}
        {timeline.map((item) =>
          item.kind === "msg" && item.msg ? (
            <MessageBubble key={`m${item.msg.id}`} msg={item.msg} onCite={onCite} />
          ) : item.quiz ? (
            <QuizCard
              key={`q${item.quiz.quiz_id}`}
              studyId={studyId}
              quiz={item.quiz}
              onGoSource={onCite}
              onRetake={onRetake}
            />
          ) : null,
        )}
        {streaming !== null && (
          <div className="flex gap-3">
            <div className="mt-1 h-7 w-7 shrink-0 rounded-full bg-violet-100 text-center text-xs leading-7 text-violet-700">
              AI
            </div>
            <div
              className="flex-1 rounded-lg border bg-white px-4 py-3 text-sm leading-7"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(streaming || "…") }}
            />
          </div>
        )}
        {streamError && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {streamError}
            <Button size="sm" variant="outline" className="ml-3" onClick={onRetry}>
              重试
            </Button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  excluded,
  generatingQuiz,
  onQuiz,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
  excluded: boolean;
  generatingQuiz: boolean;
  onQuiz: () => void;
}) {
  return (
    <div className="bg-white px-6 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          className="max-h-40 min-h-[2.6rem] flex-1 resize-none rounded-md border border-line p-2.5 text-sm outline-none focus:border-blue-500"
          placeholder="输入你的问题…（Enter 发送，Shift+Enter 换行）"
          rows={1}
          value={value}
          disabled={excluded}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        {streaming ? (
          <Button variant="outline" onClick={onStop}>
            <Square size={14} /> 停止
          </Button>
        ) : (
          <Button onClick={onSend} disabled={!value.trim() || excluded}>
            <Send size={14} />
          </Button>
        )}
      </div>
      <div className="mx-auto mt-2 flex max-w-3xl items-center justify-between">
        <span className="text-xs text-ink-soft">
          方法只改变陪学方式，不改变测验通过线；提问与阅读不产生点亮。
        </span>
        <Button size="sm" variant="gold" disabled={excluded || generatingQuiz} onClick={onQuiz}>
          考我一组
        </Button>
      </div>
    </div>
  );
}

function MessageBubble({ msg, onCite }: { msg: MessageItem; onCite: (chunkId: number) => void }) {
  const isUser = msg.role === "user";
  const refByNo = new Map((msg.refs ?? []).map((r) => [r.no, r]));
  return (
    <div className="flex gap-3">
      <div
        className={cn(
          "mt-1 h-7 w-7 shrink-0 rounded-full text-center text-xs leading-7",
          isUser ? "bg-blue-100 text-blue-700" : "bg-violet-100 text-violet-700",
        )}
      >
        {isUser ? "我" : "AI"}
      </div>
      <div className="min-w-0 flex-1">
        <div
          className={cn("rounded-lg border bg-white px-4 py-3 text-sm leading-7", isUser && "bg-blue-50/60")}
          onClick={(e) => {
            const cite = (e.target as HTMLElement).closest("[data-cite]");
            if (!cite) return;
            const ref = refByNo.get(Number(cite.getAttribute("data-cite")));
            if (ref) onCite(ref.chunk_id);
          }}
          dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
        />
        {msg.stopped && (
          <div className="mt-1 text-xs text-ink-soft">（生成已停止，以上为已生成的部分）</div>
        )}
        {!isUser && (msg.refs ?? []).length > 0 && (
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-ink-soft">
            {(msg.refs ?? []).map((r) => (
              <button key={r.no} className="hover:text-ink" onClick={() => onCite(r.chunk_id)}>
                [{r.no}] {r.title}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

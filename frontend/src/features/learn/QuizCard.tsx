import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { toast } from "sonner";
import { client, errDetail } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/basics";
import { cn } from "@/lib/utils";

export interface QuizView {
  quiz_id: number;
  created_at?: string | null;
  question_count: number;
  graded_count: number;
  practice_count: number;
  pass_line: number;
  questions: {
    no: number;
    type: string;
    graded: boolean;
    stem: string;
    options: string[] | null;
  }[];
  coverage?: { no: number; dimension: string }[];
  answered_at?: string | null;
  // 已判分面
  correct_count?: number | null;
  passed?: boolean | null;
  submitted_answers?: { no: number; choice?: unknown; text?: string }[];
  per_question?: {
    no: number;
    graded: boolean;
    correct?: boolean;
    answer?: unknown;
    explanation?: string;
    comment?: string;
    refs?: { chunk_id: number; title: string; quote: string }[];
  }[];
  lighted?: { kp_name: string; lighted_at: string | null; already_lighted: boolean } | null;
}

/** 对话流中的内嵌测验卡（B4-01/02/03）：说明明示通过线；提交前不显示答案。 */
export default function QuizCard({
  studyId,
  quiz,
  onGoSource,
  onRetake,
}: {
  studyId: number;
  quiz: QuizView;
  onGoSource: (chunkId: number) => void;
  onRetake: () => void;
}) {
  const qc = useQueryClient();
  const answered = !!quiz.answered_at;
  const [answers, setAnswers] = useState<Record<number, unknown>>({});
  const dims = quiz.coverage?.map((c) => c.dimension) ?? [];
  const dimSummary = [...new Set(dims)].join(" + ") || "细节理解与辨析 + 应用";

  const submit = useMutation({
    mutationFn: async () => {
      const body = quiz.questions.map((q) => {
        const a = answers[q.no];
        if (q.type === "short") return { no: q.no, text: String(a ?? "") };
        return { no: q.no, choice: a };
      });
      const res = await client.POST("/api/quizzes/{quiz_id}/answer", {
        params: { path: { quiz_id: quiz.quiz_id } },
        body: { answers: body },
      });
      if (res.error) throw new Error(await errDetail(res));
      return res.data as unknown as {
        passed: boolean;
        correct_count: number;
        lighted: { kp_name: string; lighted_at: string | null; already_lighted: boolean } | null;
      };
    },
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["session"] });
      void qc.invalidateQueries({ queryKey: ["tree", studyId] });
      void qc.invalidateQueries({ queryKey: ["studies"] });
      if (data.passed) {
        toast.success(`${data.lighted?.kp_name ?? "节点"} 已点亮`);
      } else {
        toast.error(`还差 ${quiz.pass_line - (data.correct_count ?? 0)} 题，先不点亮，没有任何损失`);
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const missing = quiz.questions
    .filter((q) => q.graded && answers[q.no] === undefined)
    .map((q) => q.no);

  return (
    <div className="rounded-lg border bg-white p-4" data-quiz={quiz.quiz_id}>
      <div className="mb-3 rounded bg-paper px-3 py-2 text-xs text-ink-soft">
        考一组：{quiz.graded_count} 道计分题，对 {quiz.pass_line} 题点亮本节点
        {quiz.practice_count > 0 && `；另附 ${quiz.practice_count} 道简答练习不计分`}
        。覆盖题型：{dimSummary}。
      </div>

      <div className="space-y-4">
        {quiz.questions.map((q) => (
          <QuestionRow
            key={q.no}
            q={q}
            quiz={quiz}
            answer={answers[q.no]}
            onAnswer={(v) => setAnswers((s) => ({ ...s, [q.no]: v }))}
            onGoSource={onGoSource}
          />
        ))}
      </div>

      {!answered && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-ink-soft">
            {missing.length ? `第 ${missing.join("、")} 题未作答` : "提交后立即判分；通过线固定不变"}
          </span>
          <Button disabled={missing.length > 0 || submit.isPending} onClick={() => submit.mutate()}>
            {submit.isPending ? "判分中…" : "提交答案"}
          </Button>
        </div>
      )}

      {answered && <AnsweredFooter quiz={quiz} studyId={studyId} onGoSource={onGoSource} onRetake={onRetake} />}
    </div>
  );
}

function QuestionRow({
  q,
  quiz,
  answer,
  onAnswer,
  onGoSource,
}: {
  q: QuizView["questions"][number];
  quiz: QuizView;
  answer: unknown;
  onAnswer: (v: unknown) => void;
  onGoSource: (chunkId: number) => void;
}) {
  const per = quiz.per_question?.find((p) => p.no === q.no);
  const answered = !!quiz.answered_at;
  return (
    <div
      data-q={q.no}
      className={cn("rounded-md border p-3", !q.graded && "border-dashed bg-paper/40")}
    >
      <div className="mb-2 flex items-center gap-2 text-sm">
        <span className="font-medium">第 {q.no} 题</span>
        <Badge>{q.type === "choice" ? "单选" : q.type === "judge" ? "判断" : "简答"}</Badge>
        {!q.graded && <Badge tone="amber">练习 · 不计入成绩</Badge>}
        {answered && q.graded && (
          <Badge tone={per?.correct ? "gold" : "default"}>{per?.correct ? "答对" : "答错"}</Badge>
        )}
      </div>
      <p className="text-sm">{q.stem}</p>

      {q.type === "short" ? (
        answered ? (
          <div className="mt-2 space-y-1 text-sm">
            <p className="text-ink-soft">你的回答：{shortAnswerText(quiz, q.no)}</p>
            {per?.comment && (
              <p className="rounded bg-paper p-2 text-sm">
                评价：{per.comment}
                {per.refs?.[0] && (
                  <button className="bo-cite ml-2" onClick={() => onGoSource(per.refs![0].chunk_id)}>
                    回到原文
                  </button>
                )}
              </p>
            )}
          </div>
        ) : (
          <textarea
            className="mt-2 w-full rounded-md border border-line p-2 text-sm outline-none focus:border-blue-500"
            rows={3}
            placeholder="用自己的话回答（不计入成绩）"
            value={String(answer ?? "")}
            onChange={(e) => onAnswer(e.target.value)}
          />
        )
      ) : (
        <div className="mt-2 space-y-1.5">
          {(q.options ?? ["A. 正确", "B. 错误"]).map((opt, i) => {
            const value = q.type === "judge" ? i === 0 : opt.trim()[0].toUpperCase();
            const selected =
              q.type === "judge"
                ? answer === (i === 0)
                : String(answer ?? "").toUpperCase().startsWith(String(value));
            return (
              <label
                key={i}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm",
                  selected ? "border-blue-500 bg-blue-50" : "hover:bg-black/5",
                  answered && per?.answer !== undefined && isCorrectOption(q, per.answer, value) && "border-lighted bg-amber-50",
                )}
              >
                <input
                  type="radio"
                  className="accent-blue-600"
                  disabled={answered}
                  checked={selected}
                  onChange={() => onAnswer(value)}
                />
                {opt}
              </label>
            );
          })}
          {answered && per && (
            <div className="mt-1 text-xs text-ink-soft">
              正确答案：<b>{String(per.answer)}</b>。{per.explanation}
              {per.refs?.[0] && (
                <button className="bo-cite ml-2" onClick={() => onGoSource(per.refs![0].chunk_id)}>
                  回到原文
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function isCorrectOption(q: QuizView["questions"][number], correct: unknown, value: unknown): boolean {
  if (q.type === "judge") return correct === value;
  return String(correct).toUpperCase().startsWith(String(value));
}

function shortAnswerText(quiz: QuizView, no: number): string {
  const s = quiz.submitted_answers?.find((a) => a.no === no);
  return s?.text ?? "（未作答）";
}

function AnsweredFooter({
  quiz,
  studyId,
  onGoSource,
  onRetake,
}: {
  quiz: QuizView;
  studyId: number;
  onGoSource: (chunkId: number) => void;
  onRetake: () => void;
}) {
  const nav = useNavigate();
  const passed = quiz.passed;
  const lighted = quiz.lighted;
  if (passed) {
    return (
      <div className="relative mt-4 overflow-hidden rounded-lg bg-gradient-to-b from-amber-50 to-white p-6 text-center">
        <div className="bo-particles mx-auto mb-2 inline-block relative">
          <span className="text-lighted">●</span>
        </div>
        <div className="text-lg font-semibold">{lighted?.kp_name ?? "本节点"} 已点亮</div>
        <div className="mt-1 text-sm text-ink-soft">
          {quiz.correct_count} 题对 {quiz.graded_count} · 通过线 {quiz.pass_line}
          {lighted?.already_lighted && " · 原有点亮保留"}
        </div>
        <p className="mt-2 text-xs text-ink-soft">
          点亮代表当前通过；长期记忆验证将随复习体系（后续版本）加入。
        </p>
        <div className="mt-4 flex justify-center gap-2">
          <Button variant="outline" onClick={() => nav(`/studies/${studyId}`)}>
            返回技能树
          </Button>
          <Button variant="gold" onClick={onNext(nav, studyId)}>
            学下一个 →
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="mt-4 rounded-lg bg-red-50 p-4 text-center">
      <div className="font-medium text-red-700">
        {quiz.correct_count} / {quiz.graded_count}，还差 {quiz.pass_line - (quiz.correct_count ?? 0)} 题。先不点亮，没有任何损失。
      </div>
      <div className="mt-3 flex justify-center gap-2">
        <Button variant="outline" size="sm" onClick={() => {
          const firstRef = quiz.per_question?.find((p) => p.refs?.length)?.refs?.[0];
          if (firstRef) onGoSource(firstRef.chunk_id);
        }}>
          <BookOpen size={14} /> 回到原文
        </Button>
        <Button variant="outline" size="sm" onClick={onRetake}>
          <RefreshCw size={14} /> 再考一组新题
        </Button>
      </div>
    </div>
  );
}

function onNext(nav: NavigateFunction, studyId: number) {
  return () => {
    // 学下一个：回到树（树上有“继续学习”与全部未点亮单元）
    nav(`/studies/${studyId}`, { state: { justLighted: true } });
  };
}

import createClient from "openapi-fetch";
import type { paths, components } from "./schema";

// schema 路径已含 /api 前缀，baseUrl 留空避免叠加
export const client = createClient<paths>({ baseUrl: "" });

export type KnowledgeNode = components["schemas"]["KnowledgeNode"];
export type KnowledgeTree = components["schemas"]["KnowledgeTree"];
export type StudyItem = components["schemas"]["StudyItem"];
export type StudyDetail = components["schemas"]["StudyDetail"];
export type OutlineStatus = components["schemas"]["OutlineStatus"];
export type OutlineEventItem = components["schemas"]["OutlineEventItem"];
export type ExcludeImpact = components["schemas"]["ExcludeImpact"];
export type SessionDetail = components["schemas"]["SessionDetail"];
export type MessageItem = components["schemas"]["MessageItem"];
export type MessageRef = components["schemas"]["MessageRef"];
export type QuizPublic = components["schemas"]["QuizPublic"];
export type PipelineProgress = components["schemas"]["PipelineProgress"];
export type DeleteImpact = components["schemas"]["DeleteImpact"];
export type RestorePreview = components["schemas"]["RestorePreview"];
export type SettingsPayload = components["schemas"]["SettingsPayload"];
export type UsageRow = components["schemas"]["UsageRow"];
export type NotePayload = components["schemas"]["NotePayload"];
export type ChunkDetail = components["schemas"]["ChunkDetail"];
export type NodeContent = components["schemas"]["NodeContent"];
export type ProgressInfo = components["schemas"]["ProgressInfo"];

/** 从后端响应取 detail 文案（错误统一 {"detail": ...}）。 */
export async function errDetail(res: { error?: unknown }): Promise<string> {
  const e = res.error as { detail?: string } | undefined;
  return e?.detail ?? "请求失败";
}

export interface ApiErrorPayload {
  detail: string;
  retryable?: boolean;
}

/** POST + SSE（EventSource 不支持 POST，用 fetch 流式读取）。 */
export async function postSSE(
  url: string,
  body: unknown,
  handlers: {
    onDelta?: (text: string) => void;
    onDone?: (data: { message?: MessageItem }) => void;
    onError?: (data: ApiErrorPayload) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
    signal,
  });
  if (!resp.ok || !resp.body) {
    let payload: ApiErrorPayload = { detail: `请求失败（${resp.status}）`, retryable: resp.status >= 500 };
    try {
      payload = (await resp.json()) as ApiErrorPayload;
    } catch {
      /* 保留默认 */
    }
    handlers.onError?.(payload);
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf("\n\n");
    while (sep !== -1) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      sep = buffer.indexOf("\n\n");
      let event = "message";
      const dataLines: string[] = [];
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      } catch {
        continue;
      }
      if (event === "delta") handlers.onDelta?.(String(data.text ?? ""));
      else if (event === "done") handlers.onDone?.(data as { message?: MessageItem });
      else if (event === "error")
        handlers.onError?.(data as unknown as ApiErrorPayload);
    }
  }
}

/** 遍历树节点。 */
export function walkTree(nodes: KnowledgeNode[], fn: (n: KnowledgeNode) => void): void {
  for (const n of nodes) {
    fn(n);
    walkTree(n.children ?? [], fn);
  }
}

export function flattenTree(nodes: KnowledgeNode[]): KnowledgeNode[] {
  const out: KnowledgeNode[] = [];
  walkTree(nodes, (n) => out.push(n));
  return out;
}

/** Markdown 极简渲染：仅允许少量标签，严格消毒（P1-06）。 */
export function renderMarkdown(text: string): string {
  const escape = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const inline = (s: string) =>
    escape(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(
        /\[([^\]]+)\]\(#chunk-(\d+)\)/g,
        '<a class="bo-cite" data-chunk="$2">$1</a>',
      )
      .replace(/\[(\d{1,2})\]/g, '<sup class="bo-cite" data-cite="$1">[$1]</sup>');
  const lines = text.split("\n");
  const out: string[] = [];
  let inQuote = false;
  let listOpen = false;
  const closeList = () => {
    if (listOpen) {
      out.push("</ul>");
      listOpen = false;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("> ")) {
      if (!inQuote) {
        closeList();
        out.push("<blockquote>");
        inQuote = true;
      }
      out.push(`<p>${inline(line.slice(2))}</p>`);
      continue;
    }
    if (inQuote) {
      out.push("</blockquote>");
      inQuote = false;
    }
    if (/^#{1,6}\s/.test(line)) {
      closeList();
      const level = Math.min(line.match(/^#+/)![0].length + 1, 6);
      out.push(`<h${level}>${inline(line.replace(/^#+\s*/, ""))}</h${level}>`);
      continue;
    }
    if (/^[-*]\s/.test(line)) {
      if (!listOpen) {
        out.push("<ul>");
        listOpen = true;
      }
      out.push(`<li>${inline(line.slice(2))}</li>`);
      continue;
    }
    closeList();
    if (line.trim() === "") continue;
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  if (inQuote) out.push("</blockquote>");
  return out.join("");
}

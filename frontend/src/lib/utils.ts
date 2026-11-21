import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtDate(v: string | null | undefined): string {
  if (!v) return "";
  const d = new Date(v);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const yest = new Date(now.getTime() - 86400_000).toDateString() === d.toDateString();
  if (sameDay) return "今天";
  if (yest) return "昨天";
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

export function fmtDateTime(v: string | null | undefined): string {
  if (!v) return "";
  const d = new Date(v);
  return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}

/** 按书记忆的偏好（树视图、折叠状态等，不落库——技术方案 §10）。 */
export function bookPref<T>(studyId: number, key: string, fallback: T, value?: T): T {
  const k = `bo.pref.${studyId}.${key}`;
  if (value !== undefined) {
    localStorage.setItem(k, JSON.stringify(value));
    return value;
  }
  const raw = localStorage.getItem(k);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export const STATUS_LABEL: Record<string, string> = {
  unlearned: "未学",
  learning: "学习中",
  lighted: "已点亮",
};

export const SCHEMES = [
  { value: "guided", label: "带我学", hint: "先给提示，让你自己走完推理" },
  { value: "lecture", label: "讲给我听", hint: "直接给清楚的解释" },
  { value: "drill", label: "帮我过关", hint: "高密度考练，只改密度不改通过线" },
] as const;

import { expect, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

export const BOOK = `第一章 Agent 导论

Agent 是能够感知环境、做出决策并执行动作的系统。本章介绍基本组成与运行循环。

1.1 什么是 Agent

Agent 的核心是决策循环：观察、思考、行动。信息筛选的目标是保留与当前任务直接相关的证据，而不是收集得越多越好。

1.2 Agent 的组成

Agent 通常由感知、记忆、规划与执行模块组成。记忆模块决定它能利用多少历史信息；规划模块把目标拆成可执行的步骤。

第二章 上下文工程

上下文窗口并不是越长越好。信息筛选的目标，是保留与当前任务直接相关的证据。压缩不是简单缩短文字，而是降低无关信息对注意力的干扰。

2.1 信息筛选

筛选标准有三条：任务相关性、时效性与可信度。资料放得更全反而可能让回答更差，因为信噪比下降了。

2.2 信息压缩

压缩的本质是取舍：优先保留结论与关键证据，过程性细节可以按需取用。

第三章 附录 习题答案

这里是各章习题的参考答案，不是学习内容。
`;

export function bookFile(): string {
  const p = join(HERE, "fixtures");
  mkdirSync(p, { recursive: true });
  writeFileSync(join(p, "book.txt"), BOOK, "utf-8");
  return join(p, "book.txt");
}

export const epubFile = () => join(HERE, "assets", "sample.epub");
export const pdfFile = () => join(HERE, "assets", "sample.pdf");

export const MD_BOOK = `# E2E Markdown 书

## 1.1 检索补足

检索补足只取与当前问题相关的切片，信噪比优先于覆盖率。

![示意图](fig.png)

## 1.2 引用重挂

应用规划后引用随新树重挂，向量与切片零重算。
`;

export function mdFile(): string {
  const p = join(HERE, "fixtures");
  mkdirSync(p, { recursive: true });
  writeFileSync(join(p, "book.md"), MD_BOOK, "utf-8");
  return join(p, "book.md");
}

/** 上传一本书，停在导入页。ai = 勾选「使用 AI 规划」（此时会自动弹消耗确认，页面其余部分对辅助技术隐藏）。 */
export async function uploadBook(
  page: Page,
  name: string,
  { ai = false, file }: { ai?: boolean; file?: string } = {},
): Promise<void> {
  await page.goto("/studies/new");
  await page.fill("#book-name", name);
  await page.setInputFiles('input[type="file"]', file ?? bookFile());
  if (ai) await page.getByRole("checkbox", { name: "使用 AI 规划", exact: false }).check();
  await page.getByRole("button", { name: "导入并查看技能树" }).click();
  if (ai) return;
  // 等基础目录可用（按钮变为精确的「查看技能树 →」，非提交按钮）
  await expect(page.getByRole("button", { name: "查看技能树 →", exact: true })).toBeVisible({
    timeout: 60_000,
  });
}

export async function createBook(page: Page, name: string): Promise<void> {
  await uploadBook(page, name);
  await page.getByRole("button", { name: "查看技能树 →", exact: true }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
}

export const consumeDialog = (page: Page) =>
  page.getByRole("dialog").filter({ hasText: "开始 AI 规划前，先确认消耗" });
export const proposalDialog = (page: Page) =>
  page.getByRole("dialog").filter({ hasText: "确认 AI 规划建议" });

/** 星图页书菜单「···」→「AI 规划…」：未勾选的书从这里补启动（B6-06.2）。 */
export async function openPlanningFromMenu(page: Page): Promise<void> {
  await page.getByRole("button", { name: "书菜单" }).click();
  await page.getByText("AI 规划…", { exact: true }).click();
}

/** 进入章内路径并点第一个学习单元的“开始学习”。 */
export async function openFirstUnit(page: Page): Promise<void> {
  // 停留星盘：点第一个章星进入章内路径
  await page.locator("[data-stop], .group").first();
  const stars = page.locator("section .group");
  await stars.first().waitFor({ timeout: 20_000 });
  await stars.first().click();
  // 章内路径「起点在底部」：DOM 序倒排，最后一个按钮才是书中第一个学习单元
  const learnBtn = page.getByRole("button", { name: "开始学习" }).last();
  await learnBtn.waitFor({ timeout: 20_000 });
  await learnBtn.click();
  await expect(page.getByText("节点状态与口径")).toBeVisible({ timeout: 30_000 });
}

/** 按节点标题直接进入学习页（原文双视图用，不依赖星盘交互）。 */
export async function openUnitByTitle(page: Page, studyName: string, title: string): Promise<number> {
  const list = (await (await page.request.get("/api/studies")).json()) as { id: number; name: string }[];
  const study = list.find((s) => s.name === studyName);
  if (!study) throw new Error(`study not found: ${studyName}`);
  interface Node {
    id: number;
    name: string;
    children?: Node[];
  }
  const flat: Node[] = [];
  const walk = (ns: Node[]) => ns.forEach((n) => { flat.push(n); walk(n.children ?? []); });
  walk(((await (await page.request.get(`/api/studies/${study.id}/knowledge`)).json()) as { nodes: Node[] }).nodes);
  const node = flat.find((n) => n.name === title);
  if (!node) throw new Error(`node not found: ${title}`);
  await page.goto(`/studies/${study.id}/learn/${node.id}`);
  await expect(page.getByText("节点状态与口径")).toBeVisible({ timeout: 30_000 });
  return node.id;
}

/** 按桩答案作答：Q1=B Q2=C Q3=错 Q4=错；练习随意。 */
export async function answerQuiz(page: Page, correct: boolean): Promise<void> {
  // 进行中的测验卡（含简答输入框）；已判分卡的选项是 disabled
  const card = page.locator("[data-quiz]").filter({ has: page.locator("textarea") }).last();
  await expect(card).toBeVisible({ timeout: 30_000 });
  const blocks = card.locator("[data-q]");
  const count = await blocks.count();
  // 桩固定 4 计分 + 1 练习
  const picks = correct ? [2, 3, 2, 2] : [1, 1, 1, 1];
  for (let i = 0; i < Math.min(4, count); i++) {
    await blocks.nth(i).locator("label").nth(picks[i] - 1).click();
  }
  const short = card.locator("textarea");
  if (await short.count()) await short.fill("因为无关信息会分散注意力，信噪比下降。");
  await card.getByRole("button", { name: "提交答案" }).click();
}

export async function expectLighted(page: Page): Promise<void> {
  await expect(page.getByText("已点亮", { exact: false }).first()).toBeVisible({ timeout: 30_000 });
}

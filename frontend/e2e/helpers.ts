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

export async function createBook(page: Page, name: string): Promise<void> {
  await page.goto("/studies/new");
  await page.fill("#book-name", name);
  await page.setInputFiles('input[type="file"]', bookFile());
  await page.getByRole("button", { name: "导入并查看技能树" }).click();
  // 等基础目录可用（按钮变为精确的「查看技能树 →」，非提交按钮）
  const viewBtn = page.getByRole("button", { name: "查看技能树 →", exact: true });
  await expect(viewBtn).toBeVisible({ timeout: 60_000 });
  await viewBtn.click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
}

/** 进入章内路径并点第 n 个学习单元的“开始学习”。 */
export async function openFirstUnit(page: Page, nth = 0): Promise<void> {
  // 停留星盘：点第一个章星进入章内路径
  await page.locator("[data-stop], .group").first();
  const stars = page.locator("section .group");
  await stars.first().waitFor({ timeout: 20_000 });
  await stars.first().click();
  const learnBtn = page.getByRole("button", { name: "开始学习" }).nth(nth);
  await learnBtn.waitFor({ timeout: 20_000 });
  await learnBtn.click();
  await expect(page.getByText("节点状态与口径")).toBeVisible({ timeout: 30_000 });
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

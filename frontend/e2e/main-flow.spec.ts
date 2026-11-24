import { expect, test } from "@playwright/test";
import { answerQuiz, bookFile, createBook, expectLighted, openFirstUnit } from "./helpers";

test.describe.configure({ mode: "serial" });

test("主链路：添加 → 树 → 学 → 测 → 点亮 → 进入下一节点", async ({ page }) => {
  const name = `E2E主链路 ${Date.now()}`;
  await createBook(page, name);

  // 树可见：有进度数字与章
  await expect(page.getByText("已点亮", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("第一章 Agent 导论").first()).toBeVisible();

  // 进入学习（章内路径 → 开始学习）
  await openFirstUnit(page);

  // 开场讲解自动出现且带引用（B3-01）：等完成态（引用按钮只在完成消息下渲染，
  // 流式中的角标没有点击处理器，点它不会回跳）
  await page.getByRole("button", { name: /\[1\] / }).first().waitFor({ timeout: 30_000 });

  // 引用回跳：点击角标后原文出现高亮（B3-02）
  await page.locator("sup[data-cite='1']").first().click();
  await expect(page.locator(".bo-quote-highlight").first()).toBeVisible({ timeout: 10_000 });

  // 提问不改状态（B3-04）
  await page.fill("textarea", "压缩的原则是什么？");
  await page.keyboard.press("Enter");
  await expect(page.getByText("（生成已停止", { exact: false })).toHaveCount(0);
  await page.waitForTimeout(800);

  // 考一组：说明明示通过线；提交前无答案（B4-01/02）
  await page.getByRole("button", { name: "考我一组" }).click();
  const card = page.locator("[data-quiz]").last();
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByText("4 道计分题，对 3 题点亮本节点")).toBeVisible();
  await expect(card.getByText("练习 · 不计入成绩")).toBeVisible();
  expect(await card.getByText("正确答案").count()).toBe(0);

  // 全对 → 点亮（B4-03）
  await answerQuiz(page, true);
  await expectLighted(page);
  await expect(card.getByText("4 题对 4 · 通过线 3")).toBeVisible();

  // 返回技能树：进度更新（B5-01）
  await card.getByRole("button", { name: "返回技能树" }).click();
  await expect(page.getByText("1 / 5", { exact: true }).first()).toBeVisible({
    timeout: 20_000,
  });

  // 进入下一节点：进入第一个分组的章（第一章）学 1.1
  const stars = page.locator("section .group");
  await stars.nth(1).click();
  const next = page.getByRole("button", { name: "开始学习" }).first();
  await next.waitFor({ timeout: 20_000 });
  await next.click();
  await expect(page.getByText("节点状态与口径")).toBeVisible({ timeout: 30_000 });
});

test("未通过再考是新题；刷新后作答与判分一致", async ({ page }) => {
  const name = `E2E重考 ${Date.now()}`;
  await createBook(page, name);
  await openFirstUnit(page);
  await expect(page.locator("sup[data-cite='1']").first()).toBeVisible({ timeout: 30_000 });

  // 第一组：全错 → 未通过反馈
  await page.getByRole("button", { name: "考我一组" }).click();
  await answerQuiz(page, false);
  await expect(page.getByText("先不点亮，没有任何损失", { exact: false }).first()).toBeVisible();

  // 再考一组：桩换新题干（B4-02）
  await page.getByRole("button", { name: "再考一组新题" }).click();
  const card2 = page.locator("[data-quiz]").last();
  await expect(card2.getByText("（第 2 组）").first()).toBeVisible({ timeout: 30_000 });

  // 刷新后：第一组测验的逐题判分与本组题面完全一致（B4-04）
  await page.reload();
  const answered = page.locator("[data-quiz]").first();
  await expect(answered.getByText("正确答案", { exact: false }).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(answered.getByText("练习 · 不计入成绩")).toBeVisible();
});

test("点亮后重考失败不灭灯，显示原有点亮保留", async ({ page }) => {
  const name = `E2E不灭灯 ${Date.now()}`;
  await createBook(page, name);
  await openFirstUnit(page);
  await expect(page.locator("sup[data-cite='1']").first()).toBeVisible({ timeout: 30_000 });

  // 先点亮
  await page.getByRole("button", { name: "考我一组" }).click();
  await answerQuiz(page, true);
  await expectLighted(page);

  // 重考（新组）全错：不通过，但“原有点亮保留”
  await page.getByRole("button", { name: "考我一组" }).click();
  await answerQuiz(page, false);
  const failed = page.locator("[data-quiz]").last();
  await expect(failed.getByText("先不点亮，没有任何损失", { exact: false })).toBeVisible();

  // 返回树：节点仍点亮
  await page.getByRole("button", { name: "返回技能树" }).first().click();
  await expect(page.getByText("已点亮", { exact: false }).first()).toBeVisible();
});

test("排除已点亮节点弹窗预览进度变化，应用后一致且可恢复", async ({ page }) => {
  const name = `E2E排除 ${Date.now()}`;
  await createBook(page, name);
  await openFirstUnit(page);
  await expect(page.locator("sup[data-cite='1']").first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "考我一组" }).click();
  await answerQuiz(page, true);
  await expectLighted(page);

  // 回到树，切工作树视图
  await page.getByRole("button", { name: "返回技能树" }).first().click();
  await page.getByRole("button", { name: "工作树" }).click();

  // hover 已点亮的学习单元 → ··· → 排除
  const row = page.locator("div.group", { hasText: "什么是 Agent" }).first();
  await row.click({ force: true });
  await row.locator("text=···").first().click({ force: true });
  await page.getByText("排除节点", { exact: false }).click();

  // 弹窗预览：排除的正是已点亮节点，进度 1 / 5 → 0 / 4（点亮数随节点退出）
  const dialog = page.locator("[role='dialog']");
  await expect(dialog.getByText("点亮进度将从", { exact: false })).toBeVisible();
  await expect(dialog.getByText("1 / 5").first()).toBeVisible();
  await expect(dialog.getByText("0 / 4").first()).toBeVisible();
  await dialog.getByRole("button", { name: "确认排除" }).click();

  // 应用后与预览一致（B2-05）
  await expect(page.getByText("0 / 4", { exact: false }).first()).toBeVisible({ timeout: 20_000 });

  // 恢复后还原
  const excludedRow = page.locator("div.group", { hasText: "什么是 Agent" }).first();
  await excludedRow.click({ force: true });
  await excludedRow.locator("text=···").first().click({ force: true });
  await page.getByText("恢复节点").click();
  await expect(page.getByText("1 / 5", { exact: false }).first()).toBeVisible({ timeout: 20_000 });
});

test("笔记自动保存，刷新不丢", async ({ page }) => {
  const name = `E2E笔记 ${Date.now()}`;
  await createBook(page, name);
  await openFirstUnit(page);
  await expect(page.getByText("位置：", { exact: false }).first()).toBeVisible({ timeout: 30_000 });

  // 写笔记 → 自动保存（三态之一“已保存”）
  await page
    .locator("textarea")
    .last()
    .fill("# 我的想法\n过滤不是越多越好，信噪比才是关键。");
  await expect(page.getByText("已保存 ·", { exact: false }).first()).toBeVisible({ timeout: 10_000 });

  await page.reload();
  await expect(page.getByText("过滤不是越多越好", { exact: false }).first()).toBeVisible({
    timeout: 20_000,
  });
});

test("双击导入不重复建书（BUG-003 / B1-01 反例）", async ({ page }) => {
  const name = `E2E双击 ${Date.now()}`;
  await page.goto("/studies/new");
  await page.fill("#book-name", name);
  await page.setInputFiles('input[type="file"]', bookFile());
  await page.getByRole("button", { name: "导入并查看技能树" }).dblclick();

  // 等基础目录可用（与 createBook 相同的完成信号）
  const viewBtn = page.getByRole("button", { name: "查看技能树 →", exact: true });
  await expect(viewBtn).toBeVisible({ timeout: 60_000 });

  // 书架上同名卡片只有一张
  await page.goto("/studies");
  await expect(page.locator("span.truncate.font-semibold", { hasText: name })).toHaveCount(1);
});

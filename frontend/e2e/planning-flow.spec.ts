import { expect, test } from "@playwright/test";
import { consumeDialog, createBook, openPlanningFromMenu, proposalDialog, uploadBook } from "./helpers";

/** 双确认信任流程（B6-01…B6-06）：主实例，桩规划给「分组 + 合并」两条建议。 */

test("勾选 AI 规划：预检 → 消耗确认 → 生成 → 逐条确认后应用", async ({ page }) => {
  const name = `E2E规划确认 ${Date.now()}`;
  await uploadBook(page, name, { ai: true });

  // 双进度两路都在；预检通过后自动弹消耗确认（B6-02/03/05）
  await expect(page.getByText("资料向量化：", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("AI 规划：", { exact: false }).first()).toBeVisible();
  await expect(consumeDialog(page)).toBeVisible({ timeout: 30_000 });
  await expect(consumeDialog(page).getByText(/已在后台进行，无需确认/)).toBeVisible();
  await expect(consumeDialog(page).getByText(/预计 .*token/)).toBeVisible();

  // 天数 1–365、目标必填（B6-03 验收 3）
  await page.fill("#plan-days", "0");
  await expect(consumeDialog(page).getByRole("button", { name: "开始规划" })).toBeDisabled();
  await page.fill("#plan-days", "20");
  await page.fill("#plan-goal", "   ");
  await expect(consumeDialog(page).getByRole("button", { name: "开始规划" })).toBeDisabled();
  await page.fill("#plan-goal", "先过一遍，抓住主线");
  await consumeDialog(page).getByRole("button", { name: "开始规划" }).click();

  // 建议生成后弹树确认：两类操作，默认全选，带影响预估（B6-04 验收 1/5）
  await expect(proposalDialog(page)).toBeVisible({ timeout: 60_000 });
  const mergeRow = proposalDialog(page).locator("li").filter({ hasText: "基础小节合并（桩规划）" });
  await expect(mergeRow.locator("input[type=checkbox]")).toBeChecked();
  await expect(proposalDialog(page).getByText("本次将分 1 个部分、合并 1 处；", { exact: false })).toBeVisible();

  // 只应用分组
  await mergeRow.locator("input[type=checkbox]").uncheck();
  await proposalDialog(page).getByRole("button", { name: "应用所选（1/2）" }).click();

  // 回到树：分组落地、合并未动、总述写入、规划一路显示已应用
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("AI 规划：已应用")).toBeVisible();
  await expect(page.getByText("第一部分（桩规划）").first()).toBeVisible();
  await expect(page.getByText("基础小节合并（桩规划）")).toHaveCount(0);
  await expect(page.getByText("全书总述：", { exact: false }).first()).toBeVisible();

  // 事件流完整：建议 → 应用，并记下你未选的那条
  await page.getByText("结构与规划记录").click();
  await expect(page.getByText("AI 规划建议已生成")).toBeVisible();
  await expect(page.getByText(/实际应用 1 项，你未选 1 项/)).toBeVisible();
});

test("不勾选 AI 规划：纯本地路径，规划一路不显示", async ({ page, request }) => {
  const name = `E2E纯本地 ${Date.now()}`;
  await createBook(page, name);

  await expect(page.getByText("资料向量化：完成").or(page.getByText("资料向量化：进行中")).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("AI 规划：", { exact: false })).toHaveCount(0);
  await expect(page.getByText(/想按书的逻辑整理结构/)).toBeVisible();

  // 没有任何规划事件：原树就是最终结构
  const list = await (await request.get("/api/studies")).json();
  const study = list.find((s: { name: string }) => s.name === name);
  const events = await (await request.get(`/api/studies/${study.id}/outline/events`)).json();
  expect(events.some((e: { event_type: string }) => e.event_type.startsWith("planning_"))).toBe(false);
});

test("确认前在原树学习：含证据的条目默认取消；「稍后」后可续办", async ({ page, request }) => {
  const name = `E2E证据预标注 ${Date.now()}`;
  await createBook(page, name);

  // 未勾选后改主意：从书菜单补启动（B6-06 验收 2）
  await openPlanningFromMenu(page);
  await expect(consumeDialog(page)).toBeVisible({ timeout: 30_000 });
  await consumeDialog(page).getByRole("button", { name: "开始规划" }).click();
  await expect(proposalDialog(page)).toBeVisible({ timeout: 60_000 });

  // 直接关闭 = 保留建议：不启动拒绝、总述不写、状态留在待确认树（B6-04 验收 4）
  await proposalDialog(page).getByRole("button", { name: "稍后" }).click();
  await expect(proposalDialog(page)).toHaveCount(0);
  await expect(page.getByText("AI 规划：待确认树")).toBeVisible();
  await expect(page.getByText("全书总述：", { exact: false })).toHaveCount(0);
  const list = await (await request.get("/api/studies")).json();
  const study = list.find((s: { name: string }) => s.name === name);
  const events = await (await request.get(`/api/studies/${study.id}/outline/events`)).json();
  expect(events.some((e: { event_type: string }) => e.event_type === "planning_declined")).toBe(false);

  // 确认前原树照常可学；会话即学习证据
  await page.getByRole("button", { name: "继续学习 →" }).click();
  await expect(page.getByText("节点状态与口径")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "返回技能树" }).click();

  // 续办：合并涉及已学节点 → 默认取消并标注；分组不因证据被标注（B6-04 验收 2）
  await page.getByRole("button", { name: "去确认" }).click();
  const dialog = proposalDialog(page);
  await expect(dialog).toBeVisible();
  // 用标题定位：分组行的理由文案也含「合并」二字，按词过滤会命中两行
  const mergeRow = dialog.locator("li").filter({ hasText: "基础小节合并（桩规划）" });
  await expect(mergeRow.getByText("已默认取消，不能应用：子树含学习证据")).toBeVisible();
  await expect(mergeRow.locator("input[type=checkbox]")).toBeDisabled();
  await expect(mergeRow.locator("input[type=checkbox]")).not.toBeChecked();
  const groupRow = dialog.locator("li").filter({ hasText: "分组" });
  await expect(groupRow.locator("input[type=checkbox]")).toBeChecked();
  await dialog.getByRole("button", { name: "应用所选（1/2）" }).click();
  await expect(page.getByText("AI 规划：已应用")).toBeVisible();
  await expect(page.getByText("1.1 什么是 Agent").first()).toBeVisible(); // 已学节点原位保留
});

test("全部拒绝：原树不变、转「已跳过」，之后可重新规划", async ({ page }) => {
  await createBook(page, `E2E全部拒绝 ${Date.now()}`);

  await openPlanningFromMenu(page);
  await expect(consumeDialog(page)).toBeVisible({ timeout: 30_000 });
  await consumeDialog(page).getByRole("button", { name: "开始规划" }).click();
  await expect(proposalDialog(page)).toBeVisible({ timeout: 60_000 });
  await proposalDialog(page).getByRole("button", { name: "全部拒绝" }).click();
  await proposalDialog(page).getByRole("button", { name: "确认全部拒绝" }).click();

  await expect(proposalDialog(page)).toHaveCount(0);
  await expect(page.getByText("AI 规划：已跳过")).toBeVisible();
  await expect(page.getByText("全书总述：", { exact: false })).toHaveCount(0);
  await expect(page.getByText("第一部分（桩规划）")).toHaveCount(0);

  // 可重新规划（B6-04 验收 4 / B6-06）
  await openPlanningFromMenu(page);
  await expect(consumeDialog(page)).toBeVisible({ timeout: 30_000 });
});

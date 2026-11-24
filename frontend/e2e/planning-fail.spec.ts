import { expect, test } from "@playwright/test";

// 辅实例：桩规划必失败（BO_STUB_OUTLINE_FAIL）
test.use({ baseURL: "http://127.0.0.1:8766" });
import { consumeDialog, uploadBook } from "./helpers";

test("规划失败保树：仅规划失败，原目录可编辑可学习，可重试", async ({ page }) => {
  const name = `E2E规划失败 ${Date.now()}`;
  await uploadBook(page, name, { ai: true });

  // 消耗确认后才启动；失败落在 AI 规划一路，embedding 一路不受影响（B6-05 验收 3）
  await expect(consumeDialog(page)).toBeVisible({ timeout: 30_000 });
  await consumeDialog(page).getByRole("button", { name: "开始规划" }).click();
  await expect(page.getByText("AI 规划：失败")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("AI 规划未完成（仅规划失败，原目录未受影响）", { exact: false })).toBeVisible();
  await expect(page.getByText("资料向量化：失败")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重试" })).toBeVisible();

  // 树仍在：切工作树重命名一个节点（原树可编辑）
  await page.getByRole("button", { name: "查看技能树 →", exact: true }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("AI 规划：失败")).toBeVisible();
  await page.getByRole("button", { name: "工作树" }).click();
  const row = page.locator("div.group", { hasText: "什么是 Agent" }).first();
  await row.hover();
  await row.locator("text=···").first().click();
  await page.getByText("重命名", { exact: true }).click();
  await page
    .locator("[role='dialog'] input")
    .last()
    .fill("1.1 重命名后的节点");
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText("1.1 重命名后的节点").first()).toBeVisible({ timeout: 20_000 });

  // 重试入口在双进度区，点了先重新预检、通过才回到消耗确认（B6-06 验收 1/2）
  await page.getByRole("button", { name: "重试" }).click();
  await expect(consumeDialog(page)).toBeVisible({ timeout: 30_000 });
});

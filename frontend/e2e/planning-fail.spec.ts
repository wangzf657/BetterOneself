import { expect, test } from "@playwright/test";

// 辅实例：拟大纲桩必失败
test.use({ baseURL: "http://127.0.0.1:8766" });
import { createBook } from "./helpers";

test("规划失败保树：仅规划失败，原树可编辑可学习", async ({ page, request }) => {
  const name = `E2E规划失败 ${Date.now()}`;
  // 辅实例（8766）的拟大纲桩必失败
  await createBook(page, name);

  // 状态条：仅规划失败，原目录未受影响
  await expect(
    page.getByText("拟大纲未完成（仅规划失败", { exact: false }).first(),
  ).toBeVisible({ timeout: 60_000 });

  // 树仍在：切工作树重命名一个节点（原树可编辑）
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

  // 讲解与测验不受规划失败影响（B5-03 / 原型 4.6）
  const kp = await request.get("/api/studies");
  expect(kp.ok()).toBeTruthy();
});

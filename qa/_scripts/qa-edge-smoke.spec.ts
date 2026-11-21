import { expect, test } from "@playwright/test";

// TC-UI-06 Edge 冒烟：书架 → 树 → 会话可打开
test.use({ channel: "msedge" });

test("TC-UI-06 Edge 冒烟走查", async ({ page }) => {
  await page.goto("/studies");
  await expect(page.getByRole("heading", { name: "我的书" })).toBeVisible({ timeout: 15_000 });
  await page.getByText("QA-API-FLOW-03").first().locator("xpath=ancestor::div[contains(@class,'rounded')][1]").getByRole("link", { name: "查看技能树" }).click();
  await expect(page.getByText("章节星盘").or(page.getByText("工作树 · 整理操作")).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "继续学习 →" }).click();
  await expect(page.getByText("节点状态与口径")).toBeVisible({ timeout: 30_000 });
});

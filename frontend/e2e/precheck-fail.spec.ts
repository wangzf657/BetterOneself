import { expect, test } from "@playwright/test";

// 第三实例：两路预检都不通（BO_STUB_PRECHECK_FAIL=embedding,llm）
test.use({ baseURL: "http://127.0.0.1:8767" });
import { consumeDialog, uploadBook } from "./helpers";

test("预检两路皆不通：分路提示 + 查看配置，不启动任何任务，不自动重试（B6-02）", async ({ page, request }) => {
  const name = `E2E预检不通 ${Date.now()}`;
  await uploadBook(page, name, { ai: true });

  await expect(page.getByText("资料向量化：预检失败")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("AI 规划：预检失败")).toBeVisible();
  await expect(page.getByText("两路都不通：现在是纯原文阅读模式", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看配置" })).toHaveAttribute("href", "/settings");
  await expect(page.getByRole("button", { name: "重试" })).toHaveCount(2);
  await expect(consumeDialog(page)).toHaveCount(0); // LLM 没通，进不了消耗确认（B6-02 验收 2）

  // 不自动重试：等一会儿，embedding 仍停在预检失败，没有启动过
  const list = await (await request.get("/api/studies")).json();
  const study = list.find((s: { name: string }) => s.name === name);
  const before = await (await request.get(`/api/studies/${study.id}/progress`)).json();
  expect(before.embedding.status).toBe("precheck_failed");
  expect(before.outline.status).toBe("precheck_failed");
  await page.waitForTimeout(5000);
  const after = await (await request.get(`/api/studies/${study.id}/progress`)).json();
  expect(after.embedding.status).toBe("precheck_failed");
  expect(after.outline.status).toBe("precheck_failed");

  // 原树照常可学：预检不通不阻塞基础学习路径
  await page.getByRole("button", { name: "查看技能树 →", exact: true }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("两路都不通：现在是纯原文阅读模式", { exact: false })).toBeVisible();
});

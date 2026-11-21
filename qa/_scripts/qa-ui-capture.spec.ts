import { expect, test, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const TD = "D:/workspace/ai/BetterOneself/qa/V0.1/testdata";
const SHOTS = "D:/workspace/ai/BetterOneself/qa/V0.1/screenshots";

function bookFile(name: string): string {
  return join(TD, name);
}

let consoleErrors: string[] = [];
function watchConsole(page: Page): void {
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push("pageerror: " + err.message));
}

test.describe("QA 补充证据采集", () => {
  test("CAP-1 PDF 导入页面状态（无结构 PDF）", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.fill("#book-name", "QA-UI-PDF-CAP-17");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-PDF-03.pdf"));
    await page.getByRole("button", { name: "导入并查看技能树" }).click();
    // 等待任意结果：查看技能树按钮 / 失败原因 / 无结构提示
    await page.waitForTimeout(15_000);
    await page.screenshot({ path: join(SHOTS, "cap1-pdf-import-state-1.png") });
    const body = (await page.locator("body").innerText()).slice(0, 1500);
    writeFileSync(join(SHOTS, "cap1-pdf-import-state.txt"), body, "utf-8");
    // 若出现查看技能树按钮则进入树页再截一次
    const viewBtn = page.getByRole("button", { name: /查看技能树/ }).first();
    if (await viewBtn.isVisible().catch(() => false)) {
      await viewBtn.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: join(SHOTS, "cap1-pdf-tree-state.png") });
      const treeBody = (await page.locator("body").innerText()).slice(0, 1200);
      writeFileSync(join(SHOTS, "cap1-pdf-tree-state.txt"), treeBody, "utf-8");
    }
  });

  test("CAP-2 伪 PDF 415 后表单可恢复", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.fill("#book-name", "QA-UI-BADPDF-CAP-18");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-坏文件-05.pdf"));
    await page.getByRole("button", { name: "导入并查看技能树" }).click();
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(SHOTS, "cap2-badpdf-error-state.png") });
    const body = (await page.locator("body").innerText()).slice(0, 1500);
    writeFileSync(join(SHOTS, "cap2-badpdf-error-state.txt"), body, "utf-8");
    // 恢复：重选正确 TXT 并提交
    await page.setInputFiles('input[type="file"]', bookFile("QA书-TX-01.txt"));
    const submit = page.getByRole("button", { name: /导入并查看技能树/ });
    await expect(submit).toBeEnabled({ timeout: 5000 });
    await submit.click();
    const viewBtn = page.getByRole("button", { name: "查看技能树 →", exact: true });
    await expect(viewBtn).toBeVisible({ timeout: 90_000 });
    await viewBtn.click();
    await expect(page.getByText("章节星盘").or(page.getByText("工作树 · 整理操作")).first()).toBeVisible({ timeout: 20_000 });
  });

  test("CAP-3 解析中离开再回来（修正版）", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.fill("#book-name", "QA-UI-LEAVE-CAP-19");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-TX-01.txt"));
    await page.getByRole("button", { name: "导入并查看技能树" }).click();
    await page.waitForTimeout(300);
    await page.goto("/studies");
    await expect(page.getByText("QA-UI-LEAVE-CAP-19").first()).toBeVisible({ timeout: 15_000 });
    // 状态保留：卡片显示解析状态而非消失；进入树可继续
    const card = page.getByText("QA-UI-LEAVE-CAP-19").first().locator("xpath=ancestor::div[contains(@class,'rounded')][1]");
    await expect(card.getByRole("link", { name: "查看技能树" })).toBeVisible({ timeout: 30_000 });
    await card.getByRole("link", { name: "查看技能树" }).click();
    await expect(page.getByText("章节星盘").or(page.getByText("工作树 · 整理操作")).first()).toBeVisible({ timeout: 30_000 });
    expect(consoleErrors).toEqual([]);
  });
});

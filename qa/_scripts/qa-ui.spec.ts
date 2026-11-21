import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const TD = "D:/workspace/ai/BetterOneself/qa/V0.1/testdata";

function bookFile(name: string): string {
  return join(TD, name);
}

/** 全程收集 Console 错误与未捕获异常 */
let consoleErrors: string[] = [];
test.beforeEach(() => {
  consoleErrors = [];
});
function watchConsole(page: Page): void {
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push("pageerror: " + err.message));
}

async function createBook(page: Page, name: string, file: string): Promise<void> {
  await page.goto("/studies/new");
  await page.fill("#book-name", name);
  await page.setInputFiles('input[type="file"]', bookFile(file));
  await page.getByRole("button", { name: "导入并查看技能树" }).click();
  const viewBtn = page.getByRole("button", { name: "查看技能树 →", exact: true });
  await expect(viewBtn).toBeVisible({ timeout: 90_000 });
  await viewBtn.click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
}

test.describe("QA 导入与边界（data_qa 实例）", () => {
  test("TC-B1-02 选择文件后书名自动带出", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-MD-02.md"));
    await expect(page.locator("#book-name")).toHaveValue(/QA书-MD-02/, { timeout: 5000 });
  });

  test("TC-B1-06b MD 导入并进树（QA-UI-MD-09）", async ({ page }) => {
    watchConsole(page);
    await createBook(page, "QA-UI-MD-09", "QA书-MD-02.md");
    // MD 按 #/## 层级：应至少有章级节点
    await expect(page.getByText("为什么需要 RAG")).toBeVisible({ timeout: 15_000 });
    expect(consoleErrors).toEqual([]);
  });

  test("TC-B1-10 重复点击导入不产生两本书", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.fill("#book-name", "QA-UI-DBLCLK-13");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-TX-01.txt"));
    const btn = page.getByRole("button", { name: "导入并查看技能树" });
    // 快速双击
    await btn.dblclick();
    const viewBtn = page.getByRole("button", { name: "查看技能树 →", exact: true });
    await expect(viewBtn).toBeVisible({ timeout: 90_000 });
    // 回书架统计同名书
    await page.goto("/studies");
    await expect(page.getByText("QA-UI-DBLCLK-13").first()).toBeVisible({ timeout: 15_000 });
    const n = await page.getByText("QA-UI-DBLCLK-13").count();
    expect(n).toBeLessThanOrEqual(1);
  });

  test("TC-B1-15 导入分步状态可见", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.fill("#book-name", "QA-UI-STEP-14");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-TX-01.txt"));
    await page.getByRole("button", { name: "导入并查看技能树" }).click();
    // 分步状态区域应出现（文件已保存 / 正在解析 / 自动目录规划 任意之一）
    await expect(
      page.getByText(/文件已保存|正在解析|自动目录规划/).first(),
    ).toBeVisible({ timeout: 10_000 });
    const viewBtn = page.getByRole("button", { name: "查看技能树 →", exact: true });
    await expect(viewBtn).toBeVisible({ timeout: 90_000 });
  });

  test("TC-B1-16 解析中离开再回来状态不丢", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.fill("#book-name", "QA-UI-LEAVE-15");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-TX-01.txt"));
    await page.getByRole("button", { name: "导入并查看技能树" }).click();
    // 解析进行中立刻离开到书架
    await page.waitForTimeout(300);
    await page.goto("/studies");
    await expect(page.getByText("QA-UI-LEAVE-15").first()).toBeVisible({ timeout: 15_000 });
    // 点书卡"查看技能树"回到同一进度
    await page.getByText("QA-UI-LEAVE-15").first().locator("xpath=ancestor::div[contains(@class,'rounded')][1]").getByRole("link", { name: "查看技能树" }).click();
    await expect(
      page.getByRole("button", { name: /查看技能树|开始学习/ }).first(),
    ).toBeVisible({ timeout: 60_000 });
  });

  test("TC-B1-08 PDF 导入（QA-UI-PDF-11）", async ({ page }) => {
    watchConsole(page);
    await createBook(page, "QA-UI-PDF-11", "QA书-PDF-03.pdf");
    // 无可靠目录的 PDF：进入 P03-F 空态 或 出现标题树
    const emptyState = page.getByText("这本书没有可用的标题结构");
    const treeOrEmpty = emptyState.or(page.getByRole("heading", { name: /QA-UI-PDF-11/ }));
    await expect(treeOrEmpty.first()).toBeVisible({ timeout: 30_000 });
  });

  test("TC-B1-09 EPUB 导入（QA-UI-EPUB-12）", async ({ page }) => {
    watchConsole(page);
    await createBook(page, "QA-UI-EPUB-12", "QA书-EPUB-04.epub");
    await expect(page.getByText("第 1 章 监督学习").first()).toBeVisible({ timeout: 30_000 });
    expect(consoleErrors).toEqual([]);
  });

  test("TC-B1-11/12 伪 PDF 解析失败可读，可更换文件重走解析", async ({ page }) => {
    watchConsole(page);
    await page.goto("/studies/new");
    await page.fill("#book-name", "QA-UI-BADPDF-16");
    await page.setInputFiles('input[type="file"]', bookFile("QA书-坏文件-05.pdf"));
    await page.getByRole("button", { name: "导入并查看技能树" }).click();
    // 提交即 415：预期提交前/后出现可读原因
    await expect(
      page.getByText(/不是有效的 PDF|不支持|签名校验失败/).first(),
    ).toBeVisible({ timeout: 15_000 });
    // 更换为正确 TXT 后重新解析成功
    await page.getByRole("button", { name: "更换文件" }).first().click();
    await page.setInputFiles('input[type="file"]', bookFile("QA书-TX-01.txt"));
    const viewBtn = page.getByRole("button", { name: /查看技能树/ }).first();
    await expect(viewBtn).toBeVisible({ timeout: 90_000 });
  });

  test("TC-UI-04 会话 <1024 三页签模式", async ({ page }) => {
    watchConsole(page);
    await page.setViewportSize({ width: 900, height: 800 });
    await page.goto("/studies");
    // 用已有书进入学习页：QA-API-FLOW-03 的继续学习
    await page.getByText("QA-API-FLOW-03").first().locator("xpath=ancestor::div[contains(@class,'rounded')][1]").getByRole("button", { name: "继续学习" }).click();
    await expect(page.getByText("节点状态与口径")).toBeVisible({ timeout: 30_000 });
    // 页签模式：出现 原文/陪学/笔记 页签
    await expect(page.getByRole("button", { name: /原文/ }).first()).toBeVisible({ timeout: 10_000 });
    expect(consoleErrors).toEqual([]);
  });

  test.afterEach(async () => {
    if (consoleErrors.length) {
      mkdirSync("D:/workspace/ai/BetterOneself/qa/V0.1/logs", { recursive: true });
      writeFileSync(
        `D:/workspace/ai/BetterOneself/qa/V0.1/logs/console-${Date.now()}.log`,
        consoleErrors.join("\n---\n"),
        "utf-8",
      );
    }
  });
});

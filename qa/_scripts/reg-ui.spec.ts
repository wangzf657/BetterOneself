import { expect, test } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// 回归 UI 用例（修复后）：BUG-001 设置两节只改一项 / BUG-003 三连击 / BUG-004 星盘三形态 / BUG-005 排除身份。
// 证据截图存 qa/V0.1/screenshots/reg/。前置：study2 已预排除(单元26+容器27)；study8=链路书(TX01 桩分组)；
// study9=MD02(无部分层)；study10=PDF03(无章层)。
const SHOT = path.join(__dirname, "..", "V0.1", "screenshots", "reg");
const TX = path.join(__dirname, "..", "V0.1", "testdata", "QA书-TX-01.txt");
fs.mkdirSync(SHOT, { recursive: true });

test.describe.configure({ mode: "serial" });

async function shot(page: import("@playwright/test").Page, name: string) {
  await page.screenshot({ path: path.join(SHOT, name) });
}

test("REG-001 设置两节只改一项：密钥与未提交字段不丢（BUG-001）", async ({ page }) => {
  await page.goto("/settings");
  const llm = page.locator("section", { has: page.locator("h2", { hasText: "讲解与测验服务" }) });
  const base = llm.locator('input[placeholder="https://api.example.com/v1"]');
  const model = llm.locator('input[placeholder="模型名，如 glm-4.7"]');
  const key = llm.locator("input").nth(2);
  const save = llm.getByRole("button", { name: "保存本节" });

  await expect(base).toBeVisible();
  // 前置（API 阶段已写入）：密钥已保存 → 掩码提示存在
  await expect(key).toHaveAttribute("placeholder", /已保存/);

  // ① LLM 节只改 base_url → 保存 → 密钥不丢（BUG-001 核心）
  await base.fill("http://ui-reg.test/v9");
  await save.click();
  await expect(page.getByText("已保存", { exact: true }).first()).toBeVisible({ timeout: 8000 });
  await page.reload();
  await expect(base).toHaveValue("http://ui-reg.test/v9");
  await expect(key).toHaveAttribute("placeholder", /已保存/);
  await expect(model).toHaveValue("");
  await shot(page, "reg-001-llm-only-baseurl.png");

  // ② LLM 节只改 model → 密钥与 base_url 仍保持
  await model.fill("ui-model-x");
  await save.click();
  await page.reload();
  await expect(model).toHaveValue("ui-model-x");
  await expect(base).toHaveValue("http://ui-reg.test/v9");
  await expect(key).toHaveAttribute("placeholder", /已保存/);

  // ③ 界面零明文密钥
  const content = await page.content();
  expect(content).not.toContain("sk-reg-secret");
  await shot(page, "reg-001-llm-only-model.png");

  // ④ embed 节只改 base_url → model/密钥保持（跨节隔离）
  const emb = page.locator("section", { has: page.locator("h2", { hasText: "资料处理服务" }) });
  const embBase = emb.locator('input[placeholder="https://api.siliconflow.cn/v1"]');
  const embModel = emb.locator('input[placeholder="BAAI/bge-m3"]');
  const embKey = emb.locator("input").nth(2);
  await embBase.fill("http://emb-ui-reg.test");
  await emb.getByRole("button", { name: "保存本节" }).click();
  await page.reload();
  await expect(embBase).toHaveValue("http://emb-ui-reg.test");
  await expect(embModel).toHaveValue("emb-m");
  await expect(embKey).toHaveAttribute("placeholder", /已保存/);
  await shot(page, "reg-001-embed-only-baseurl.png");

  // ⑤ 显式清除密钥：只清 key，base_url/model 保持
  await llm.getByRole("button", { name: "清除密钥" }).click();
  await expect(llm.getByText("将在保存时清除")).toBeVisible();
  await save.click();
  await page.reload();
  await expect(key).toHaveAttribute("placeholder", /sk-…（保存后只显示掩码）/);
  await expect(base).toHaveValue("http://ui-reg.test/v9");
  await expect(model).toHaveValue("ui-model-x");
  await shot(page, "reg-001-llm-clearkey.png");
});

test("REG-003 三连击导入不重复建书（BUG-003 UI 补充）", async ({ page }) => {
  const name = `回归UI三连击 ${Date.now()}`;
  await page.goto("/studies/new");
  await page.fill("#book-name", name);
  await page.setInputFiles('input[type="file"]', TX);
  const btn = page.getByRole("button", { name: "导入并查看技能树" });
  await btn.click({ clickCount: 3 });
  await page.waitForTimeout(150);
  await btn.click({ timeout: 3000 }).catch(() => {}); // 迟到的一击
  await expect(page.getByRole("button", { name: "查看技能树 →", exact: true })).toBeVisible({ timeout: 60_000 });
  await page.goto("/studies");
  await expect(page.locator("span.truncate.font-semibold", { hasText: name })).toHaveCount(1);
  await shot(page, "reg-003-triple-click-shelf.png");
});

async function starSequence(page: import("@playwright/test").Page): Promise<string[]> {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll("h3, div.w-36 > div.line-clamp-2"))
      .map((e) => (e.textContent || "").trim())
      .filter((t) => /^第[一二三四五]章|^第一部分|^QA书-/.test(t)),
  );
}

test("REG-004 形态A 部分组按书序先行：部分→章序不颠倒（BUG-004）", async ({ page }) => {
  await page.goto("/studies/8");
  await expect(page.getByText("章节星盘 · 进度与导航")).toBeVisible({ timeout: 15000 });
  const seq = await starSequence(page);
  const expectOrder = ["第一部分", "第一章", "第二章", "第三章", "第四章", "第五章"];
  const idx = expectOrder.map((p) => seq.findIndex((t) => t.startsWith(p)));
  idx.forEach((v, i) => expect(v, `${expectOrder[i]} 未找到`).not.toBe(-1));
  for (let i = 1; i < idx.length; i++) expect(idx[i], `${expectOrder[i]} 应在 ${expectOrder[i - 1]} 之后`).toBeGreaterThan(idx[i - 1]);
  await shot(page, "reg-004-shapeA-part-first.png");
});

test("REG-004 形态B 无部分层书：单散章无虚构组名（BUG-004）", async ({ page }) => {
  await page.goto("/studies/9");
  await expect(page.getByText("章节星盘 · 进度与导航")).toBeVisible({ timeout: 15000 });
  const h3Count = await page.locator("h3").count();
  expect(h3Count, "无部分层书不应出现分组标题").toBe(0);
  const seq = await starSequence(page);
  expect(seq.length, "唯一根章作为散章呈现").toBe(1);
  expect(seq[0]).toContain("QA书-MD-02");
  await shot(page, "reg-004-shapeB-no-part.png");
});

test("REG-004 形态C 无章层书：P03-F 专门空态，不虚构星盘（BUG-004/B2）", async ({ page }) => {
  await page.goto("/studies/10");
  // 空树渲染 P03-F 整页空态（无视图切换条、无星盘）
  await expect(page.getByText("这本书没有可用的标题结构")).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("button", { name: "重新识别" })).toBeVisible();
  await expect(page.getByRole("button", { name: "星盘", exact: true })).toHaveCount(0);
  expect(await page.locator("div.w-36").count(), "无章层不虚构星盘").toBe(0);
  await shot(page, "reg-004-shapeC-p03f-empty.png");
});

test("REG-005 已排除学习单元详情显示单元身份，不误标容器（BUG-005）", async ({ page }) => {
  await page.goto("/studies/2");
  await page.getByRole("button", { name: "工作树", exact: true }).click();
  await page.locator("select").selectOption("excluded");
  // 已排除的学习单元（根级单元，无子）
  await page.locator("div.h-9", { hasText: "第五章 附录 习题答案" }).first().click();
  const aside = page.locator("aside");
  await expect(aside).toBeVisible();
  await expect(aside.getByText("学习单元（已排除）")).toBeVisible();
  await expect(aside.getByText(/容器 · \d+ \/ \d+ 点亮/)).toHaveCount(0);
  await shot(page, "reg-005-excluded-unit.png");
  // 已排除的容器（有子）：仍应显示容器身份（修复不误伤真容器）
  await page.locator("div.h-9", { hasText: "第一部分（桩规划）" }).first().click();
  await expect(aside.getByText(/容器 · \d+ \/ \d+ 点亮/)).toBeVisible();
  await expect(aside.getByText("学习单元（已排除）")).toHaveCount(0);
  await shot(page, "reg-005-excluded-container.png");
});

test("REG-005b 未排除容器详情不受修复影响", async ({ page }) => {
  await page.goto("/studies/3");
  await page.getByRole("button", { name: "工作树", exact: true }).click();
  await page.locator("div.h-9", { hasText: "第一部分（桩规划）" }).first().click();
  const aside = page.locator("aside");
  await expect(aside.getByText(/容器 · \d+ \/ \d+ 点亮/)).toBeVisible();
  await shot(page, "reg-005b-normal-container.png");
});

import { expect, test, type Locator, type Page } from "@playwright/test";
import { createBook, epubFile, mdFile, openUnitByTitle, pdfFile, uploadBook } from "./helpers";

/** 原文双视图（B6-07）：默认解析文本、按 location 双向定位、按格式保真渲染。 */

/** 断言元素滚进原文面板可视区（Playwright 的 toBeVisible 不受滚动影响，需比对几何位置）。 */
async function expectInView(locator: Locator): Promise<void> {
  await expect
    .poll(
      () =>
        locator.evaluate((el) => {
          const pane = el.closest(".overflow-y-auto");
          if (!pane) return false;
          const r = el.getBoundingClientRect();
          const p = pane.getBoundingClientRect();
          return r.top >= p.top - 2 && r.top < p.bottom - 24;
        }),
      { timeout: 15_000 },
    )
    .toBe(true);
}

const originalBtn = (page: Page) => page.getByRole("button", { name: "原文", exact: true });
const parsedBtn = (page: Page) => page.getByRole("button", { name: "解析文本", exact: true });

test("TXT：默认解析文本，切原文按行定位，反向回跳对应切片", async ({ page }) => {
  const name = `E2E原文TXT ${Date.now()}`;
  await createBook(page, name);
  await openUnitByTitle(page, name, "1.1 什么是 Agent");

  // 默认解析文本（B6-07 验收 1）
  await expect(parsedBtn(page)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("section", { hasText: "观察、思考、行动" }).first()).toBeVisible();

  // 切原文：定位到切片首行（1.1 的段落行）
  await originalBtn(page).click();
  const line = page.locator("[data-line]", { hasText: "观察、思考、行动" }).first();
  await expect(line).toBeVisible();
  await expectInView(line);

  // 反向切回：定位到对应切片并高亮（匹配不到才回退）
  await parsedBtn(page).click();
  const section = page.locator("section", { hasText: "观察、思考、行动" }).first();
  await expect(section).toHaveClass(/bo-quote-highlight/, { timeout: 5_000 });
});

test("PDF：跳 location 起始页整页渲染，反向回跳对应切片", async ({ page }) => {
  const name = `E2E原文PDF ${Date.now()}`;
  await uploadBook(page, name, { file: pdfFile() });
  await page.getByRole("button", { name: "查看技能树 →", exact: true }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
  await openUnitByTitle(page, name, "1.2 Memory");

  await originalBtn(page).click();
  // 1.2 在第 3 页（location.page_start=2，展示 +1）
  await expect(page.getByText("第 3 页 / 共 3 页")).toBeVisible({ timeout: 30_000 });
  const canvas = page.locator("[data-page='3'] canvas");
  await expect.poll(() => canvas.evaluate((el) => (el as HTMLCanvasElement).width > 0), { timeout: 20_000 }).toBe(true);

  await parsedBtn(page).click();
  const section = page.locator("section", { hasText: "Memory decides" }).first();
  await expect(section).toHaveClass(/bo-quote-highlight/, { timeout: 5_000 });
});

test("EPUB：消毒片段渲染、图片走资产端点可见、标题定位；资产端点拒路径穿越", async ({ page }) => {
  const name = `E2E原文EPUB ${Date.now()}`;
  await uploadBook(page, name, { file: epubFile() });
  await page.getByRole("button", { name: "查看技能树 →", exact: true }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
  const nodeId = await openUnitByTitle(page, name, "第一章 上下文");

  await originalBtn(page).click();
  // 图片 src 被后端改写为资产端点（外链与内嵌已被消毒丢弃）
  const img = page.locator(".prose-book img");
  await expect(img).toHaveCount(1);
  await expect(img).toHaveAttribute("src", /\/api\/sources\/\d+\/assets\//);
  await expect.poll(() => img.evaluate((el) => (el as HTMLImageElement).naturalWidth > 0), { timeout: 15_000 }).toBe(true);
  // 首段文本定位：切片 1 的首段就是章标题块
  await expectInView(page.locator(".prose-book h1", { hasText: "第一章 上下文" }));

  // 资产端点路径穿越（编码后的 ..）按 404 拒绝，不抛 500（技术设计 §8.3）
  const content = (await (await page.request.get(`/api/kps/${nodeId}/content`)).json()) as { source_id: number };
  const sid = content.source_id;
  expect((await page.request.get(`/api/sources/${sid}/assets/%2e%2e%2fbook.txt`)).status()).toBe(404);
  expect((await page.request.get(`/api/sources/${sid}/assets/OEBPS%2F..%2Fbook.txt`)).status()).toBe(404);
  expect((await page.request.get(`/api/sources/${sid}/assets/OEBPS%5C..%5Fsecret.txt`)).status()).toBe(404);
});

test("MD：markdown 渲染，本地相对路径图片占位注明不支持", async ({ page }) => {
  const name = `E2E原文MD ${Date.now()}`;
  await uploadBook(page, name, { file: mdFile() });
  await page.getByRole("button", { name: "查看技能树 →", exact: true }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible({ timeout: 30_000 });
  await openUnitByTitle(page, name, "1.1 检索补足");

  await originalBtn(page).click();
  // markdown 渲染 + 定位到切片首段
  await expect(page.locator(".prose-book h2", { hasText: "1.1 检索补足" })).toBeVisible();
  await expectInView(page.locator(".prose-book h2", { hasText: "1.1 检索补足" }));
  // 本地相对路径图：占位注明单文件导入不支持（技术设计 §8.2）
  await expect(page.locator("[data-md-img-placeholder='fig.png']")).toContainText("单文件导入不支持");
  // 解析文本视图不受影响（B6-07 验收 5 的兜底方向）
  await parsedBtn(page).click();
  await expect(page.locator("section", { hasText: "信噪比优先于覆盖率" }).first()).toBeVisible();
});

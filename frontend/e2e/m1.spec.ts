import { expect, test } from '@playwright/test'

// M1 主链路:建项目 → 导入 MD → 自动拆解 → 看树 → 进讲解 → 提问见引用(stub LLM)
test('M1 能学主链路', async ({ page }) => {
  const name = `E2E-${Date.now()}`

  await page.goto('/')
  await expect(page.getByText('今天该做什么')).toBeVisible()

  // 建项目
  await page.getByRole('link', { name: '去创建' }).click()
  await page.getByRole('button', { name: '新建项目' }).click()
  await page.getByPlaceholder('名称,如:学 Rust').fill(name)
  await page.getByPlaceholder('一句话目标,如:读完 RustBook 并能写 CLI 工具').fill('E2E 验证')
  await page.getByRole('button', { name: '创建', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/studies/\\d+/sources`))

  // 导入 MD
  await page.setInputFiles('input[type=file]', 'e2e/fixtures/rust.md')
  const row = page.locator('a', { hasText: 'rust' }).first()
  await expect(row).toBeVisible()
  await expect(page.getByText('就绪', { exact: true })).toBeVisible({ timeout: 30_000 })

  // 阅读页:全文与目录
  await row.click()
  await expect(page.getByText('移动语义').first()).toBeVisible()
  await expect(page.getByText('将值赋给另一个变量时')).toBeVisible()
  await page.goBack()

  // 知识点树
  await page.getByRole('link', { name: '知识点' }).click()
  await expect(page.getByText('Rust 基础').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('移动语义').first()).toBeVisible()
  await expect(page.getByText('借用', { exact: true }).first()).toBeVisible()

  // 开始学习 → 讲解会话
  await page
    .locator('div', { hasText: /^移动语义/ })
    .filter({ has: page.getByRole('button', { name: '开始学习' }) })
    .first()
    .getByRole('button', { name: '开始学习' })
    .click()
  await expect(page.getByText('学习会话 · 讲解')).toBeVisible()
  await expect(page.getByText('引导你思考')).toBeVisible()
  await expect(page.getByTestId('kp-preview')).toBeVisible() // 原文预习面板

  // 提问 → 流式回答 + 引用角标
  await page.getByPlaceholder(/就当前知识点提问/).fill('什么是移动语义?')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const chip = page.getByRole('button', { name: /来源:/ }).first()
  await expect(chip).toBeVisible({ timeout: 30_000 })

  // 点击引用 → 源文侧栏定位
  await chip.click()
  await expect(page.getByText(/源文:/).first()).toBeVisible()
})

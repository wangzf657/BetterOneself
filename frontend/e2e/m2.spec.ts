import { expect, test } from '@playwright/test'

// M2 主链路:出题 → 答错自动沉淀卡片 → 复习队列翻面四档评分
test('M2 能考主链路', async ({ page }) => {
  const name = `M2-${Date.now()}`

  // 建项目→导 MD→知识点→开始学习(与 M1 相同的入场)
  await page.goto('/studies')
  await page.getByRole('button', { name: '新建项目' }).click()
  await page.getByPlaceholder('名称,如:学 Rust').fill(name)
  await page.getByPlaceholder('一句话目标,如:读完 RustBook 并能写 CLI 工具').fill('M2 验证')
  await page.getByRole('button', { name: '创建', exact: true }).click()
  await expect(page).toHaveURL(/\/studies\/\d+\/sources/)

  await page.setInputFiles('input[type=file]', 'e2e/fixtures/rust.md')
  await expect(page.getByText('就绪', { exact: true })).toBeVisible({ timeout: 30_000 })

  await page.getByRole('link', { name: '知识点' }).click()
  await expect(page.getByText('移动语义').first()).toBeVisible({ timeout: 30_000 })
  await page
    .locator('div', { hasText: /^移动语义/ })
    .filter({ has: page.getByRole('button', { name: '开始学习' }) })
    .first()
    .getByRole('button', { name: '开始学习' })
    .click()
  await expect(page.getByText('学习会话 · 讲解')).toBeVisible()

  // 出题
  await page.getByRole('button', { name: '考我一组' }).click()
  const quizzes = page.locator('[data-testid^="quiz-"]')
  await expect(quizzes).toHaveCount(3, { timeout: 30_000 })

  // 两道单选:点第 2 个选项(stub 结构:第 1 项为正确答案,必错)→ 自动生成卡片
  const objective = page.locator('[data-testid^="quiz-"]').filter({ hasText: '单选' })
  await objective.first().getByRole('button').nth(1).click()
  await expect(objective.first().getByText('答错')).toBeVisible()
  await objective.nth(1).getByRole('button').nth(1).click()
  await expect(objective.nth(1).getByText('答错')).toBeVisible()

  // 简答:无关答案 → AI 评分不通过 + 评语
  const short = page.locator('[data-testid^="quiz-"]').filter({ hasText: '简答' })
  await short.getByPlaceholder('用自己的话回答…').fill('完全无关的答案')
  await short.getByRole('button', { name: '提交' }).click()
  await expect(short.getByText('答错')).toBeVisible({ timeout: 30_000 })
  await expect(short.getByText(/重叠不足|建议回看/)).toBeVisible()

  // 复习:顶栏入口有角标 → 翻面 → 四档评分(键盘)
  await page.getByTestId('review-entry').click()
  await expect(page.getByTestId('review-page')).toBeVisible()
  await expect(page.getByTestId('review-progress')).toHaveText(/1 \/ [123]/)

  await page.keyboard.press(' ') // 翻面
  await expect(page.getByTestId('rating-bar')).toBeVisible()
  await expect(page.getByText('来源:')).toBeVisible() // 背面含源引用(M3-05)

  await page.keyboard.press('3') // 良好
  await expect(page.getByTestId('review-progress')).toHaveText(/2 \/ [123]|3 \/ [123]/)
})

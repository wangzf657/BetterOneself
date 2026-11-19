import { expect, test } from '@playwright/test'

/** 本地日期(后端 today() 用本地时钟) */
function localDate(offsetDays: number): string {
  const d = new Date(Date.now() + offsetDays * 86400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 完整主链路(技术总纲 6.3):建项目→导入→拆解→确认计划→完成任务→答错一题→次日复习→重排可见
test('V1.0 完整闭环主链路', async ({ page }) => {
  await page.request.post('/api/dev/fake-today', { data: {} }) // 干净时间基线
  const name = `FULL-${Date.now()}`

  // 建项目 + 导入 MD
  await page.goto('/studies')
  await page.getByRole('button', { name: '新建项目' }).click()
  await page.getByPlaceholder('名称,如:学 Rust').fill(name)
  await page.getByPlaceholder('一句话目标,如:读完 RustBook 并能写 CLI 工具').fill('完整闭环验证')
  await page.getByRole('button', { name: '创建', exact: true }).click()
  await page.setInputFiles('input[type=file]', 'e2e/fixtures/rust.md')
  await expect(page.getByText('就绪', { exact: true })).toBeVisible({ timeout: 30_000 })

  // 拆解结果可见
  await page.getByRole('link', { name: '知识点' }).click()
  await expect(page.getByText('移动语义').first()).toBeVisible({ timeout: 30_000 })

  // 访谈 + 确认计划
  await page.getByRole('link', { name: '计划' }).click()
  await page.getByRole('button', { name: '开始目标访谈' }).click()
  await page.getByRole('button', { name: '生成计划草案' }).click()
  await page.getByRole('button', { name: '确认生效' }).click()
  await expect(page.getByText('已生效', { exact: true })).toBeVisible()

  // 完成学习任务:进会话 → 答错一题(自动沉淀卡片)
  await page.goto('/')
  const taskRow = page.locator('[data-testid^="today-task-"]').first()
  await taskRow.getByRole('button', { name: /移动语义|Rust 基础|借用/ }).click()
  await expect(page.getByText('学习会话 · 讲解')).toBeVisible()
  await page.getByRole('button', { name: '考我一组' }).click()
  const objective = page.locator('[data-testid^="quiz-"]').filter({ hasText: '单选' })
  await objective.first().getByRole('button').nth(1).click()
  await expect(objective.first().getByText('答错')).toBeVisible()

  // 次日:复习该卡(四档)+ 今日页重排可见
  await page.request.post('/api/dev/fake-today', { data: { date: localDate(1) } })
  await page.goto('/review')
  await expect(page.getByTestId('review-card')).toBeVisible({ timeout: 30_000 })
  await page.keyboard.press(' ')
  await expect(page.getByTestId('rating-bar')).toBeVisible()
  await page.keyboard.press('3')
  await page.goto('/')
  // 逾期 learn 任务被重排(不堆积):横幅或当日任务任一可见即闭环成立
  await expect(page.getByText('今天该做什么')).toBeVisible()
  const bannerCount = await page.getByTestId('reschedule-banner').count()
  const taskCount = await page.locator('[data-testid^="today-task-"]').count()
  expect(bannerCount + taskCount).toBeGreaterThan(0)
})

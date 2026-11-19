import { expect, test } from '@playwright/test'

/** 本地日期(后端 today() 用本地时钟;toISOString 是 UTC,跨时区会算错一天) */
function localDate(offsetDays: number): string {
  const d = new Date(Date.now() + offsetDays * 86400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// M4 主链路:同一知识点连错两次 → 薄弱标记 + 次日针对性任务(带证据)
test('M4 能督促主链路', async ({ page }) => {
  // M3 结尾快进过时间(fake_today 是后端进程级状态),先重置回真实今天
  await page.request.post('/api/dev/fake-today', { data: {} })
  const name = `M4-${Date.now()}`

  // 建项目→导 MD→访谈→确认计划(复用 M3 路径)
  await page.goto('/studies')
  await page.getByRole('button', { name: '新建项目' }).click()
  await page.getByPlaceholder('名称,如:学 Rust').fill(name)
  await page.getByPlaceholder('一句话目标,如:读完 RustBook 并能写 CLI 工具').fill('M4 验证')
  await page.getByRole('button', { name: '创建', exact: true }).click()
  await page.setInputFiles('input[type=file]', 'e2e/fixtures/rust.md')
  await expect(page.getByText('就绪', { exact: true })).toBeVisible({ timeout: 30_000 })

  await page.getByRole('link', { name: '计划' }).click()
  await page.getByRole('button', { name: '开始目标访谈' }).click()
  await page.getByRole('button', { name: '生成计划草案' }).click()
  await expect(page).toHaveURL(/\/plan/)
  await page.getByRole('button', { name: '确认生效' }).click()
  await expect(page.getByText('已生效', { exact: true })).toBeVisible()

  // 进知识点会话,连错两次(单选第 2 选项必错)
  await page.getByRole('link', { name: '知识点' }).click()
  await expect(page.getByText('移动语义').first()).toBeVisible({ timeout: 30_000 })
  await page
    .locator('div', { hasText: /^移动语义/ })
    .filter({ has: page.getByRole('button', { name: '开始学习' }) })
    .first()
    .getByRole('button', { name: '开始学习' })
    .click()
  await page.getByRole('button', { name: '考我一组' }).click()
  const objective = page.locator('[data-testid^="quiz-"]').filter({ hasText: '单选' })
  await objective.first().getByRole('button').nth(1).click()
  await expect(objective.first().getByText('答错')).toBeVisible()
  await objective.nth(1).getByRole('button').nth(1).click()
  await expect(objective.nth(1).getByText('答错')).toBeVisible()

  // 知识点树出现「薄弱」标记(M4-05)
  await page.getByRole('link', { name: '知识点' }).click()
  await expect(page.getByText('薄弱', { exact: true })).toBeVisible({ timeout: 30_000 })

  // 今日页出现「针对薄弱点」任务(次日,经 fake-today 快进后可见)
  await page.request.post('/api/dev/fake-today', { data: { date: localDate(1) } })
  await page.goto('/')
  const weakRow = page.locator('[data-testid^="today-task-"]').filter({ hasText: '针对薄弱点' })
  await expect(weakRow).toBeVisible({ timeout: 30_000 })
})

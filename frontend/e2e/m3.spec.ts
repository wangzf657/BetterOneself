import { expect, test } from '@playwright/test'

/** 本地日期(后端 today() 用本地时钟;toISOString 是 UTC,跨时区会算错一天) */
function localDate(offsetDays: number): string {
  const d = new Date(Date.now() + offsetDays * 86400_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// M3 主链路:访谈 → 计划确认 → 今日任务完成 → 时间快进 → 逾期重排可见
test('M3 能规划主链路', async ({ page }) => {
  const name = `M3-${Date.now()}`

  // 建项目→导 MD→等拆解
  await page.goto('/studies')
  await page.getByRole('button', { name: '新建项目' }).click()
  await page.getByPlaceholder('名称,如:学 Rust').fill(name)
  await page.getByPlaceholder('一句话目标,如:读完 RustBook 并能写 CLI 工具').fill('M3 验证')
  await page.getByRole('button', { name: '创建', exact: true }).click()
  await expect(page).toHaveURL(/\/studies\/\d+\/sources/)
  await page.setInputFiles('input[type=file]', 'e2e/fixtures/rust.md')
  await expect(page.getByText('就绪', { exact: true })).toBeVisible({ timeout: 30_000 })

  // 访谈(M2-04)
  await page.getByRole('link', { name: '计划' }).click()
  await page.getByRole('button', { name: '开始目标访谈' }).click()
  await page.getByPlaceholder('如:能独立写 CLI 工具 / 应付面试 / 读懂源码').fill('能写 CLI')
  await page.getByRole('button', { name: '生成计划草案' }).click()
  await expect(page).toHaveURL(new RegExp(`/studies/\\d+/plan`))

  // 计划页(M2-05/06):按日分组、草案徽标、确认生效
  await expect(page.getByTestId('plan-days')).toBeVisible()
  await expect(page.getByText('草案', { exact: true })).toBeVisible()
  const day0 = page.locator('[data-testid^="plan-day-"]').first()
  await expect(day0.getByText('移动语义').first()).toBeVisible() // 依赖顺序:移动语义在借用前
  await page.getByRole('button', { name: '确认生效' }).click()
  await expect(page.getByText('已生效', { exact: true })).toBeVisible()

  // 今日页(M5-01):任务出现,点任务名进会话
  await page.goto('/')
  const taskRow = page.locator('[data-testid^="today-task-"]').first()
  await expect(taskRow).toBeVisible()
  await expect(taskRow.getByText('移动语义')).toBeVisible()
  await taskRow.getByRole('button', { name: '移动语义' }).click()
  await expect(page.getByText('学习会话 · 讲解')).toBeVisible()

  // 回今日页,标记完成
  await page.goto('/')
  await page
    .locator('[data-testid^="today-task-"]')
    .first()
    .getByRole('button', { name: '完成' })
    .click()
  await expect(page.locator('[data-testid^="today-task-"]')).toHaveCount(0)

  // 时间快进 5 天 → 逾期重排横幅(M5-02)+ 任务排进未来
  await page.request.post('/api/dev/fake-today', { data: { date: localDate(5) } })
  await page.goto('/')
  await expect(page.getByTestId('reschedule-banner')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText(/已重排/)).toBeVisible()

  // 计划页变更历史有重排记录(经项目列表进入,今日页无项目侧栏)
  await page.goto('/studies')
  await page.getByRole('link', { name }).click()
  await page.getByRole('link', { name: '计划' }).click()
  await expect(page.getByTestId('plan-events')).toBeVisible()
  await expect(page.getByText('逾期重排')).toBeVisible()
})

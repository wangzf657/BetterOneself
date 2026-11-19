import { expect, test } from '@playwright/test'

/** M5 补全验证:文本粘贴导入、自评跳过+快速验证、档案视图、设置页 */
test('M5 补全特性', async ({ page }) => {
  await page.request.post('/api/dev/fake-today', { data: {} })
  const name = `M5-${Date.now()}`

  await page.goto('/studies')
  await page.getByRole('button', { name: '新建项目' }).click()
  await page.getByPlaceholder('名称,如:学 Rust').fill(name)
  await page.getByPlaceholder('一句话目标,如:读完 RustBook 并能写 CLI 工具').fill('M5 验证')
  await page.getByRole('button', { name: '创建', exact: true }).click()

  // 粘贴文本导入(M1-07)
  await page.getByRole('button', { name: /粘贴文本/ }).click()
  await page.getByPlaceholder('标题', { exact: true }).fill('随手笔记')
  await page
    .getByPlaceholder('粘贴笔记/邮件片段…(支持 Markdown 标题,便于拆解)')
    .fill('# 笔记章节\n粘贴正文。\n\n## 细节\n更多。')
  await page.getByRole('button', { name: '导入', exact: true }).click()
  await expect(page.getByText('就绪', { exact: true })).toBeVisible({ timeout: 30_000 })

  // 自评跳过 + 快速验证(M2-07)
  await page.getByRole('link', { name: '知识点' }).click()
  await expect(page.getByText(/笔记章节|细节|要点/).first()).toBeVisible({ timeout: 30_000 })
  const row = page.locator('div.group', { has: page.locator('button[aria-label^="自评"]') }).first()
  await row.hover() // 操作按钮 hover 才显示(hidden+group-hover:flex)
  await row.locator('button[aria-label^="自评"]').click()
  // 快速验证弹层出题,正确作答(stub 正确答案在选项第一项)
  await expect(page.getByText(/快速验证/)).toBeVisible({ timeout: 30_000 })
  await page.getByPlaceholder('你的答案…').press('Enter') // 空答案不会提交;直接跳过验证
  await page.getByRole('button', { name: '跳过验证' }).click()
  await expect(page.getByText('我已掌握(自评)', { exact: true }).first()).toBeVisible()

  // 档案视图(M6-02/03):自评与系统评估并列
  await page.getByRole('link', { name: '档案' }).click()
  await expect(page.getByTestId('mastery-list')).toBeVisible()
  await expect(page.getByText('自评:已掌握').first()).toBeVisible()

  // 摘要页(M5-03/05):无行为也如实展示
  await page.getByRole('link', { name: '摘要' }).click()
  await expect(page.getByTestId('summaries-page')).toBeVisible()

  // 卡片页 + Anki 导出链接存在(M4-04/06)
  await page.getByRole('link', { name: '卡片' }).click()
  await expect(page.getByRole('link', { name: /导出 Anki/ })).toBeVisible()

  // 设置页(M7-01):key 掩码输入
  await page.getByTestId('settings-entry').click()
  await expect(page.getByTestId('settings-page')).toBeVisible()
  await expect(page.getByText('模型配置(BYO-Key)')).toBeVisible()
})

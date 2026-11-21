# BUG-003 快速重复点击"导入并查看技能树"产生两本书

| 字段 | 内容 |
|---|---|
| 缺陷 ID | BUG-003 |
| 标题 | 双击导入按钮创建两个同名学习项目（违反 B1-01 反例"重复点击不得生成两本书"） |
| 模块 | B1-01 / P01 添加一本书（frontend/src/features/studies/NewStudyPage.tsx） |
| 严重级别 | **P1 严重**（产生重复数据；有删除路径兜底故不定 P0） |
| 复现概率 | 高（自动化双击必现；真实用户快速双击可触发） |

## 前置条件
`/studies/new`，已填书名并选择文件。

## 复现步骤
1. 填书名"QA-UI-DBLCLK-13"，选择 QA书-TX-01.txt。
2. 对"导入并查看技能树"按钮执行快速双击（Playwright `dblclick`，间隔约数十毫秒）。
3. 回到 `/studies` 统计同名卡片。

## 预期结果
仅创建一本书（幂等或提交后禁用）。

## 实际结果
创建两本书：GET /api/studies 中 `QA-UI-DBLCLK-13` 出现两条（id=11、id=12，均解析成功 9 个学习单元）。书架渲染两张同名卡片。

## 证据
- DB 直查（只读）：studies 表两条同名记录；
- 运行记录：qa/V0.1/logs/qa-ui-results/（TC-B1-10 失败上下文）；
- 代码事实（供定位）：`NewStudyPage.tsx` 每次提交生成新 `crypto.randomUUID()` 作为 Idempotency-Key（第 27 行），幂等键形同虚设；提交守卫 `if (!create.isPending)` 与按钮 `disabled={create.isPending}` 依赖 React 状态更新时序，双击竞态下第二次点击仍可触发 `mutate()`。

## 影响分析
- 重复书会污染书架、重复占用解析/检索资源；用户可能误入重复书继续学习导致记录分裂。
- 需求映射：B1-01 反例明确禁止；页面清单 P01"重复点击不得生成两本书"。

## 修复记录（2026-11-21）

- 根因：前端每次 `mutate()` 生成新 `crypto.randomUUID()` 作幂等键，后端幂等去重永不命中；`create.isPending` 是异步 React 状态，双击竞态下第二次点击仍可触发。
- 修复：`NewStudyPage.tsx` 幂等键进页生成一次（`useRef`）+ `submittingRef` 同步提交标志（提交即置位、失败复位允许重试）；后端 `studies.create_study` 补并发同键兜底——幂等记录主键冲突（IntegrityError）时回滚后按键返回已有书。
- 回归：E2E 新增 `main-flow.spec.ts::双击导入不重复建书（BUG-003 / B1-01 反例）`（dblclick → 书架同名卡片恰 1 张）通过；后端 `test_create_idempotent_concurrent_same_key`（3 线程并发同键仅 1 本）通过；pytest 59 passed，E2E 7 passed。

## 回归验证（2026-11-21 修复后）

**结论：修复确认，关闭。** 详见 [06-regression-report.md](../06-regression-report.md)（API/单测/链路证据在 `logs/reg/`，UI 证据在 `screenshots/reg/`）。

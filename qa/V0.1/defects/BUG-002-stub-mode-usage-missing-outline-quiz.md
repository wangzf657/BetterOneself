# BUG-002 桩模式下用量统计缺失 outline/quiz 场景

| 字段 | 内容 |
|---|---|
| 缺陷 ID | BUG-002 |
| 标题 | `BO_LLM_STUB=1` 时用量只记录 tutor 场景，outline/quiz 场景请求不入账 |
| 模块 | B5-04 服务配置与用量可见（backend/app/core/llm.py） |
| 严重级别 | **P2 一般**（桩/开发模式数据不完整；真实 LLM 路径有 record_usage，不受影响） |
| 复现概率 | 必现（桩模式下） |

## 前置条件
`BO_LLM_STUB=1` 启动后端；导入一本书（触发 outline + embedding 尝试）并生成/作答测验。

## 复现步骤
1. 桩模式下完成：导入 → 拟大纲 → 生成测验 → 答题 → 讲解/提问。
2. `GET /api/usage` 或设置页"用量"表。

## 预期结果
按场景出现 `outline`、`tutor`、`quiz` 行（embed 未配置时无行合理）。

## 实际结果
仅 `{"date":"2026-11-21","scene":"tutor","requests":6}` 一行。设置页用量表同。

## 证据
- qa/V0.1/logs/api/（usage 响应）
- 数据库直查（只读）：`usage_days` 表仅 1 行 tutor；
- 代码事实：`llm.py complete()` 非流式补全（outline_planner/quiz/简答评语使用）的桩分支 `if get_config().llm_stub: return stub_llm.complete(...)` 在 `record_usage` 之前提前返回；`stream()` 的桩分支则调用了 `record_usage`（因此 tutor 有行）。

## 影响分析
- B5-04 验收"按日期和场景查看 AI 用量"在开发/自测模式下口径不完整，容易掩盖真实模式下的用量问题；
- E2E 无法通过桩模式验证用量完整性。

## 修复记录（2026-11-21）

- 根因：`llm.py complete()` 桩分支在 `record_usage` 之前提前返回。
- 修复：`backend/app/core/llm.py` 桩分支补 `record_usage(db, scene, 0, 0)`（与 stream() 桩分支同口径）。
- 连带发现并修复（修复时 E2E 暴露）：`answer_quiz` 原先在条件认领 UPDATE（持 SQLite 写锁）之后才调评语 LLM，`record_usage` 的第二条连接被阻塞 5s busy timeout 后写失败——用量既丢、判分响应延迟恰好撞破 E2E 5s 默认超时。已重排为**内存判分与评语先行（不持写锁）→ 条件更新原子认领 → 判分+点亮同一事务提交**，"条件更新原子认领 / 判分与点亮一次落库"契约不变（流程图 §测验点亮 仍一致）。
- 回归：`tests/test_progress_lighting.py::test_answer_quiz_records_usage_without_lock_stall`（判分入账 ≥2 次 + 响应 <3s）、`tests/test_studies_security.py::test_stub_complete_records_usage` 通过；pytest 59 passed，E2E 7 passed。

## 回归验证（2026-11-21 修复后）

**结论：修复确认，关闭。** 详见 [06-regression-report.md](../06-regression-report.md)（API/单测/链路证据在 `logs/reg/`，UI 证据在 `screenshots/reg/`）。

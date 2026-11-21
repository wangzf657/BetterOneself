# 06 回归测试报告（BetterOneself V0.1 · 修复后）

## 1. 回归概况

| 项 | 内容 |
|---|---|
| 触发 | 首轮完整测试（[04-test-report.md](04-test-report.md)，结论 PASS WITH ISSUES）交付 5 个缺陷后，开发完成修复，按报告 §9 回归重点执行定向 + 全量回归 |
| 被测版本 | feat/v1.0 工作区修复版（基于 `e43e328`，11 个文件改动 +195/−29：backend 7、frontend 4，未提交） |
| 回归时间 | 2026-11-21 20:00 – 20:45（首轮同日） |
| 回归环境 | 与首轮同拓扑隔离：backend 8000（`BO_LLM_STUB=1`，**全新** `data_qa_reg`）+ Vite 5176（localhost，代理 8000）；用户 `backend/data/` 未做任何读写 |
| 修复内容核对（diff 审阅） | BUG-001 `put_settings` 改 `exclude_unset`；BUG-002 `complete()` 桩分支补 `record_usage`；BUG-003 前端固定幂等键+同步提交标志、后端 `IntegrityError` 同键竞态回读；BUG-004 星盘 `buildGroups` 按书序原位排布；BUG-005 详情面板 `wasLearningUnit` 识别；另含 quiz 判分/认领次序重排（判分先行、认领后置）与 4 个新增后端单测 + 1 个双击 E2E |

## 2. 逐缺陷回归结果（5 / 5 修复确认）

| ID | 级别 | 回归验证 | 关键证据 |
|---|---|---|---|
| BUG-001 设置部分保存清空字段 | **P1** | ✅ **修复确认**。API 三语义 16 项全过：只改 base_url → model/api_key 保持；只换密钥 → base_url/model 保持；显式 `null` 仅清除目标字段；空对象/空节 no-op；llm 与 embed 节互不波及；掩码（`sk-****et-b`）、DB Fernet 密文、日志零明文全部保持。UI 两节"只改一项"4 场景 + 显式清除密钥路径全过 | `logs/reg/api-regression.json` R1.*；`screenshots/reg/reg-001-*.png` ×4 |
| BUG-002 桩模式用量缺场景 | P2 | ✅ **修复确认**。桩模式导入（outline 规划）、开场/提问（tutor）、生成测验（quiz）后 `/api/usage` 三场景全部入账（outline requests=13、quiz=1 等），行结构完整 | `logs/reg/api-regression.json` R2.3–R2.6 |
| BUG-003 双击导入重复建书 | **P1** | ✅ **修复确认**。API：同键两次返回同 id（201/201，id=1）；**并发 5 连发同键全成功且同一本书**（ids={2}，后端 IntegrityError 竞态分支生效）；不同键正常建新书；书架与 DB 层均无重复（3 键 3 书）。UI：双击（项目新增 E2E ok 6）+ 三连击 + 迟到一击均只建 1 本 | `logs/reg/api-regression.json` R3.*；`screenshots/reg/reg-003-triple-click-shelf.png`；`logs/reg/pnpm-e2e.log` |
| BUG-004 星盘排序与书序不符 | P3 | ✅ **修复确认**。三种形态：A 部分组按书序先行（第一部分含第一/二章在最前，第三/四/五章随后，截图与 DOM 序双验证）；B 无部分层书单散章呈现、无虚构组名；C 无章层书 P03-F 专门空态、不虚构星盘（视图切换条不出现） | `screenshots/reg/reg-004-shapeA-part-first.png`、`shapeB`、`shapeC` |
| BUG-005 排除单元误标容器 | P3 | ✅ **修复确认**。已排除根级单元详情显 **"学习单元（已排除）"**（不再出现"容器 · 0 / 0 点亮"）；已排除容器仍显"容器 · x / y 点亮"（修复无误伤）；未排除容器不变 | `screenshots/reg/reg-005-excluded-unit.png`、`reg-005-excluded-container.png`、`reg-005b-normal-container.png` |

## 3. 全量自动化回归（防劣化，真实运行结果）

| 检查 | 首轮 | 本轮 | 变化说明 |
|---|---|---|---|
| 后端 pytest | 55 passed / 3 skipped | **59 passed / 3 skipped** | +4 为修复新增单测（设置三语义、幂等竞态、桩记账、判分次序），全过 |
| ruff / mypy | 绿 | **绿**（42 source files） | — |
| eslint / tsc --noEmit | 绿 | **绿** | — |
| 项目 E2E（pnpm e2e） | 6/6 | **7/7**（23.2s） | +1 为"双击导入不重复建书（BUG-003 / B1-01 反例）"，通过 |
| 核心 API 域链路（40 步断言） | 39/40（脚本误报） | **40/40** | 见 §4.1；含 quiz 判分/认领重排后的完整 学→测→点亮→重考保留→排除恢复 链路 |
| UI 定向回归（7 用例） | — | **7/7** | REG-001/003/004×3/005×2，见 `qa/_scripts/reg-ui.spec.ts` |

quiz.py 次序重排的专项风险（判分先行、条件更新认领后置）已由：并发作答语义单测（新增）、E2E 重考/点亮保留用例、链路 40 步（含未达线→重考新题→达线点亮→已点亮重考保留全链路）三重覆盖，无回归。

## 4. 回归过程记录（非缺陷）

### 4.1 链路脚本 TC-B2-07 陈旧断言（首轮即存在的误报，本轮澄清）
首轮与首轮日志（`logs/api/api_flow_test_study9.log`）均显示该步 FAIL（39/40）。经与 [接口设计.md](../../docs/v0.1/technical/接口设计.md) 119 行核对：契约返回 `{progress_before, progress_after, lighted_affected}`，脚本断言的 `lighted_before/total_before` 字段名不存在；修正字段后进一步发现断言的期望值也错（链路在排除步骤前已点亮该单元，`before` 应为 (1,9) 而非 (0,9)）。按语义修正后 40/40——**产品行为始终正确**（预览 1/9→0/8、lighted_affected=1，与应用结果一致），系 QA 脚本两代陈旧断言叠加的误报，非产品缺陷。

### 4.2 其他记录
- 首轮旧 UI spec（qa-ui / qa-ui-capture / qa-edge-smoke）因 testDir 整目录被执行而混入运行：其用例绑定首轮数据目录的书籍 ID，在本轮新环境按预期失败/跳过，**不在回归范围、未计入结果**（回归以 reg-ui.spec.ts 为准）。
- 观察到一项**正确降级行为**：embed 配置假地址后 `status="failed"` + 错误"embedding 全部失败（可重试）" + 降级说明文案，符合 B5-04 语义（仅失去跨节点细节检索补足，讲解/测验/原文不受影响）。
- 会话"幂等取或建"（同节点重复建会话返回已有会话，接口设计.md:144）行为与文档一致，链路脚本首次重跑的 409 为状态污染所致，换新书后通过。

## 5. 回归结论

## **PASS（修复确认，零回归）**

- 5/5 缺陷（含 2 个 P1）修复确认，原始复现路径全部关闭；
- 全量自动化（pytest 59 / E2E 7 / 链路 40 步 / 静态四项）零回归；
- 修复未引入新缺陷；discover 的唯一异常均为 QA 脚本自身断言问题。

首轮报告结论 **PASS WITH ISSUES** 的两个不放行理由（BUG-001 违反 B5-02 隐含语义、BUG-003 违反 B1-01 明确反例）均已消除，V0.1 在"桩模式可验证面"内升级为 **PASS**。

**不变的限制**：真实 LLM 输出质量人工抽评与讲解风格差异验证仍 **BLOCKED**（无 API Key）——该项与桩模式无关，作为合并前最后一道人工验证的建议维持不变（04 报告 §9）。

## 6. 遗留与建议

1. **合并前人工验证**：配置真实 API Key 后抽评拟大纲与讲解质量（B1/B3 验收中"不能由 mock 替代"的部分）。
2. **UX 台账**：05-ux-evaluation.md 中 8 项台账级优化点（详情浮层遮挡、悬停可发现性等）不在本轮修复范围，可作为后续小优化批次。
3. **提交建议**：修复改动已通过回归，建议按需求 ID 引用提交（B5-02 / B1-01 / B4 / B2-06 / B2-05），并保留本轮新增测试（4 单测 + 1 E2E）。
4. QA 回归数据目录 `backend/data_qa_reg` 与全部证据（screenshots/reg、logs/reg）保留备查，确认无需后可删除。

## 证据索引

```text
qa/V0.1/
├── 06-regression-report.md          本报告
├── logs/reg/
│   ├── api-regression.json          BUG-001/002/003 API 断言结果（27/28，唯一 FAIL 为重跑基线残留）
│   ├── chain-study8.log             核心 API 链路 40/40
│   ├── pnpm-e2e.log                 项目 E2E 7/7
│   ├── pytest.log                   59 passed / 3 skipped
│   ├── eslint.log / tsc.log         前端静态检查
│   ├── backend-8000.log             回归后端运行日志（含零明文密钥核验）
│   └── ui-results/                  UI 回归 trace 与产物
├── screenshots/reg/                 REG-001/003/004×3/005×2 证据截图 ×11
qa/_scripts/
├── reg_api.py / reg-ui.spec.ts / reg.qa.config.ts   回归脚本（新增）
└── V0.1/scripts/api_flow_test.py    链路脚本（TC-B2-07 断言按契约修正）
```

# 02 测试计划（BetterOneself V0.1）

> 日期：2026-11-21｜被测版本：feat/v1.0 HEAD e43e328｜测试者：QA Engineer

## 1. 测试目标

1. 验证 V0.1 全部 22 条需求（B1-01…B5-04）的验收标准逐条成立，含每条 P0 的**反例**。
2. 验证页面清单（P01–P05）逐页走查表全部项目。
3. 验证自动化测试（后端 pytest/ruff/mypy、前端 lint/tsc/e2e）真实通过，不以"配置存在"为准。
4. 按"只测试、不修复"原则输出缺陷清单与测试报告。

## 2. 测试范围

| 范围 | 内容 | 方法 |
|---|---|---|
| 功能 | 22 条需求正向验收 + 页面走查表 | 真实界面走查（浏览器）+ API 复核 |
| 边界异常 | 空值/非法格式/超大文件/重复提交/刷新后退/并发重复请求/不存在 ID | API（curl）+ 界面 |
| 安全 | 密钥明文泄露（日志/页面/LLM 上下文）、XSS 注入、Origin/CORS、路径穿越、越权 ID | API（curl）+ 日志审查 |
| UI/交互 | 布局遮挡溢出、加载/空/错误三态、反馈准确性、折叠与页签 | 真实界面走查 |
| 兼容 | Chrome（主）、Edge（抽测）；1280×800 / 1920×1080；<1024 页签模式 | 浏览器 |
| 性能 | 首屏加载、书架/树列表、导入耗时、SSE 流式首字延迟（单用户体验级） | 浏览器 + curl 计时 |
| UX 评估 | 七维评分 + 行业对标 + 优化建议（逐页面覆盖） | 真实操作 + 截图证据 |

**明确不在范围**：真实 LLM 输出质量抽评（无 key，BLOCKED 单列）；专业压测；移动端真机；多语言。

## 3. 测试策略

- **分层**：
  1. 静态检查层：后端 pytest / ruff / mypy，前端 lint / tsc --noEmit——先跑通，作为"自动化测试通过"验收的证据。
  2. E2E 层：项目自带 Playwright 用例（pnpm e2e，双实例桩后端）。
  3. API 层：curl 直接打接口，覆盖异常/边界/安全红线（用独立 QA 数据目录 `data_qa`）。
  4. 界面层：Playwright 浏览器人工式走查全部 5 页 + 走查表专项（含截图证据）。
- **AI 全程使用 `BO_LLM_STUB=1` 确定性桩**（项目自带，E2E/开发用）：不触网、不花 token；拟大纲失败场景用 `BO_STUB_OUTLINE_FAIL=1` 辅实例。
- **数据隔离**：QA 专用 `BO_DATA_DIR=backend/data_qa`；不触碰用户既有 `backend/data/`。每本书用可追踪命名（QA书-TX-01 等）。
- **执行顺序**：P0 核心闭环 → P1 主功能 → P2 边界异常 → P3 UI/兼容 → 安全 → 性能 → UX 评估。
- **反例优先**：22 条需求中每条 P0 的反例（如"不得静默丢失会话""不得同题重复"）必须逐条验证并留证据。

## 4. 环境与数据准备

- 后端 QA 实例：127.0.0.1:8000，`BO_LLM_STUB=1`、`BO_DATA_DIR=data_qa`。
- 前端：Vite dev server 5173（CORS 已允许）。
- 测试样书（qa/V0.1/testdata/）：
  - `QA书-TX-01`：多章 TXT（含子标题、附录章）——主链路；
  - `QA书-MD-02`：Markdown（`#`/`##` 标题树）——MD 格式；
  - `QA书-PDF-03`：自造小 PDF——PDF 格式；
  - `QA书-EPUB-04`：自造最小合法 EPUB——EPUB 格式；
  - `QA书-坏文件-05`：损坏/伪格式文件（.pdf 实为文本、超大文件、空文件）——异常。
- 浏览器自动化：ZCode 内置 Playwright 浏览器（browser-use 技能）。
- 截图/日志路径：qa/V0.1/screenshots/、qa/V0.1/logs/。

## 5. 通过/失败判据

- 用例状态仅 PASS / FAIL / BLOCKED / NOT RUN；通过率 = PASS/(PASS+FAIL)。
- 缺陷分级 P0/P1/P2/P3 按测试要求 §五。
- 总结论按 PASS / PASS WITH ISSUES / FAIL / INCONCLUSIVE 四选一，不弱化问题。

## 6. 交付物

qa/V0.1/{01-system-analysis,02-test-plan,03-test-cases,04-test-report,05-ux-evaluation}.md + defects/ + screenshots/ + logs/ + scripts/。

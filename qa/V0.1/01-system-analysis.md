# 01 系统功能分析（BetterOneself V0.1）

> 测试工程师产出｜日期：2026-11-21｜被测版本：feat/v1.0 分支 HEAD e43e328（V0.1 最薄闭环全量实现）

## 1. 项目技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 / FastAPI / SQLAlchemy 2 + SQLite（backend/.venv 实测 3.12.16） |
| 解析 | Docling（PDF）、自研 EPUB/TXT/Markdown 解析（app/ingest/） |
| LLM | OpenAI 兼容协议 BYO-Key；`BO_LLM_STUB=1` 确定性桩替代真实 LLM（不触网）；embedding 独立配置 |
| 前端 | React 19 + Vite + TS strict / shadcn/ui + Tailwind 4 / TanStack Query |
| E2E | Playwright 1.65.1（frontend/playwright.config.ts，双后端实例 8765/8766） |
| 数据 | SQLite 单文件 backend/data/betteroneself.db + uploads/ 目录；Alembic 单 revision 建库 |

## 2. 系统功能模块（对照 22 条需求）

- **B1 一项目一本书**：创建学习项目（书名+单文件）、四格式解析、导入进度与失败态、重试/换文件。
- **B2 技能树式知识骨架**：零 LLM 目录识别（标题规则）、AI 拟大纲（分组/排除/拆分/合并/总述，失败保留原树）、树编辑（重命名/排除/恢复/解散分组/恢复原目录）、节点状态（未学/学习中/已点亮/待确认/已排除）。
- **B3 学习会话**：三框布局（左原文/中陪学/右笔记）、AI 开场讲解（SSE 流式）、自由提问、学习方法三选一、节点笔记自动保存。
- **B4 测验与点亮**：按节点生成 3–5 计分客观题+至多 1 简答练习、固定通过线映射（3→2/4→3/5→4）、通过点亮、重考新题、已点亮重考失败保留、测验回看。
- **B5 进度与底线**：全书点亮进度下钻、密钥安全（掩码/加密落库）、AI 未配置不阻塞、设置页服务与用量。

## 3. 页面与路由清单

| 编号 | 页面 | 路由 | 源码 |
|---|---|---|---|
| P01 | 添加一本书 | `/studies/new` | frontend/src/features/studies/NewStudyPage.tsx |
| P02 | 我的书（首页） | `/studies`（`/` 重定向） | frontend/src/features/studies/StudiesPage.tsx |
| P03 | 书页·技能树 | `/studies/:studyId` | frontend/src/features/tree/TreePage.tsx 等 |
| P04 | 学习会话 | `/studies/:studyId/learn/:nodeId` | frontend/src/features/learn/LearnPage.tsx |
| P05 | 设置 | `/settings` | frontend/src/features/settings/SettingsPage.tsx |
| — | 学习方法抽屉 | 全站覆盖层 | frontend/src/features/settings/MethodDrawer.tsx |

树页含三种视图：星盘（StarMapView）、章内路径（ChapterPathView）、工作树（WorkTreeView）+ 详情面板（DetailPanel）+ 事件抽屉（EventsDrawer）。

## 4. API 接口概览（实测 openapi.json / 路由源码）

- `/api/studies`：POST 创建（multipart，Idempotency-Key 头）、GET 列表/详情、PATCH 改名/scheme、GET delete-impact、DELETE、POST source/replace、GET progress
- `/api/sources`：POST /{id}/reparse（202）、POST /{id}/reembed（202）
- `/api/studies/{id}/knowledge|outline-status|outline/replan|outline/events|outline/restore-preview|outline/restore-original`
- `/api/kps/{id}`：GET exclude-impact、PATCH 重命名、POST exclude/restore/dissolve-group
- `/api/studies/{id}/sessions` POST（get_or_create）、`/api/sessions/{id}` GET、POST opening（SSE）/chat（SSE）、PATCH scheme、POST quizzes、POST /quizzes/{id}/answer、GET /kps/{id}/quizzes
- `/api/kps/{id}/content|note|lighting-evidence`、`/api/chunks/{id}`
- `/api/settings` GET/PUT、`/api/usage` GET（from/to）

## 5. 核心业务流程

导入（保存文件→解析→目录识别→后台 AI 拟大纲→embedding）→ 技能树（查看/编辑/规划状态）→ 学习会话（开场讲解→提问→笔记）→ 测验（生成→作答→判分→点亮/新题再考）→ 进度（树/书架/星盘同口径）。

## 6. 用户角色与权限

单机单用户、无账号体系（技术方案 §11）。权限面收窄为：Origin/CORS 校验（OriginCheckMiddleware）、上传边界（300MB / PDF 2000 页 / EPUB 条目与解压上限）、路径穿越防护。无登录/多角色，相关用例仅覆盖越权访问面与安全红线（密钥明文、XSS）。

## 7. 外部依赖

- 真实 LLM（BYO-Key）：本次测试不使用真实 key、不触网（测试纪律），讲解/测验/拟大纲全部走 `BO_LLM_STUB=1` 确定性桩。
- embedding 服务：同上，桩/未配置降级路径纳入测试。

## 8. 测试环境及启动方式（本机实测）

- 后端：`backend/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`（uv 不在 PATH，直接用现有 venv，不装新依赖）
- 前端：`pnpm dev`（5173）或后端托管 dist（SPA fallback 已挂载）
- 静态检查：venv 内 pytest 9.2.0 / ruff / mypy；前端 pnpm lint / tsc --noEmit
- E2E：`pnpm e2e`（自动拉起 8765 桩实例 + 8766 规划必败实例，独立数据目录 data_e2e1/2）
- **数据隔离**：用户已有 backend/data/（含 1 本既往书），QA 全程使用独立 `BO_DATA_DIR=data_qa`，不触碰业务数据。

## 9. 行业对标清单（体验评估阶段复用，均公开可查）

| 分类 | 对标产品 | 关键体验特征（来源：官方站点/公开文档，执行阶段再核实引用） |
|---|---|---|
| 读书+学习 | Readwise Reader（readwise.io/read） | 原文/批注联动、快进阅读队列、ghost reader 提问 |
| 电子书阅读 | Kindle Web/Cloud（read.amazon.com） | 字体排版、进度同步、笔记导出 |
| 间隔复习/测验 | Anki（apps.ankiweb.net） | 自评四档、逐卡统计；Quizlet（quizlet.com） | 学习模式多形态、即时判分反馈 |
| 知识管理 | Notion（notion.com）/ Obsidian（obsidian.md） | 块级编辑、双链、全局命令面板 |
| AI 陪学 | Khanmigo（khanacademy.org/khan-labs） | 苏格拉底式引导、不直接给答案 |
| 结构化学习 | Coursera（coursera.org） | 大纲导航+进度徽章+视频/测验穿插 |

> 本产品是"单本书陪学"工具，对标组合取"阅读器 + 测验 + 树形进度"三类。

## 10. 尚未明确的需求与风险

1. **LLM 输出质量人工抽评**：需求列表明确要求"真实样书人工抽评，不能由 mock 测试替代"。本次测试无真实 key，桩输出为固定文案——该项记 BLOCKED，报告中单列。
2. 桩 `_quiz_counter` 为模块级全局计数器，重启才归零；对"同节点重复生成不得同题"的判定依赖计数器递增，属实现细节而非产品行为，真实 LLM 下需另验。
3. 用户库中已有 1 本既往书（backend/data/），非本次测试产物；测试只读不改。
4. 移动端/多浏览器兼容性未列入 V0.1 硬性验收，按 P3 抽测 Chrome/Edge 桌面分辨率。
5. 性能只做单用户体验级检查（首屏、列表、导入耗时），不做压测（符合测试要求 §2.6 约束）。

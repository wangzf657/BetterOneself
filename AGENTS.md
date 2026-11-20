# BetterOneself

一个陪你学透一本书的 Agent。当前为 V0.1 单机自用验证版，范围是最薄闭环：导入一本书 → 技能树式知识骨架（AI 按书的逻辑拟大纲）→ 左原文、中陪学、右笔记 → 通过节点测验点亮。计划、复习、卡片、掌握档案等在 docs/v0.1/后续候选/，不属于当前范围。

## 文档是一等公民——动代码前先读文档

### 产品文档：回答“为什么做、怎么用、怎样算完成”

| 文档 | 内容 | 什么时候读 |
|---|---|---|
| [docs/v0.1/product/需求分析.md](docs/v0.1/product/需求分析.md) | 用户、问题、范围、概念与核心闭环 | 不确定“该不该做”时 |
| [docs/v0.1/product/需求列表.md](docs/v0.1/product/需求列表.md) | 22 条需求、验收标准与反例（B1-01…） | 每个功能的完成定义；commit 引用需求 ID |
| [docs/v0.1/product/页面清单.md](docs/v0.1/product/页面清单.md) | 路由、逐页布局、状态、弹窗与异常 | 新增或改动页面前 |
| [docs/v0.1/product/原型设计.md](docs/v0.1/product/原型设计.md) | 关键屏线框、视觉层级与点击流 | 调整信息层级与交互前 |

### 技术文档：回答“怎样实现、怎样验证”

| 文档 | 内容 | 什么时候读 |
|---|---|---|
| [docs/v0.1/technical/技术方案.md](docs/v0.1/technical/技术方案.md) | 技术选型、模块、导入、skills、安全与测试 | 写代码、改依赖或核心流程前 |
| [docs/v0.1/technical/数据模型.md](docs/v0.1/technical/数据模型.md) | 目标表结构、迁移与统计口径 | 改 models/ 前；先写设计再迁移 |
| [docs/v0.1/technical/流程图.md](docs/v0.1/technical/流程图.md) | 导入、拟大纲、目录编辑、会话、测验点亮与进度流程 | 改 service 编排与事务前 |
| [docs/v0.1/technical/接口设计.md](docs/v0.1/technical/接口设计.md) | 目标 API 契约与需求映射 | 改 api/、schemas/ 或前端请求前 |

### 决策与历史

- [docs/v0.1/决策记录.md](docs/v0.1/决策记录.md)：当前关键取舍与已否决方案。
- [docs/v0.1/后续候选/](docs/v0.1/后续候选/)：延后候选（计划与督促、复习与卡片、掌握档案与强度分级、学习增强、数据与导出、书籍分享），不属于当前范围。
- [docs/v0.1/注意事项.md](docs/v0.1/注意事项.md)：前身实验失败教训的浓缩；重建时逐条对照。
- [docs/research/](docs/research/)：竞品调研，只作设计依据，不代替当前需求。

**文档与代码冲突时：先用评审后的新结论改文档，再改代码。产品与技术文档分开打磨，不用字段或接口代替产品需求，也不在产品文档里预设实现。技术方案中的【目标】与【待验证】不得当成已完成。**

## 技术栈速览

- backend：Python 3.12 / FastAPI / SQLAlchemy 2 + SQLite（sqlite-vec）/ Docling；无 LangGraph、py-fsrs（V0.1 会话为顺序流；复习在后续候选）
- frontend：React 19 + Vite + TS strict / shadcn/ui + Tailwind 4 / TanStack Query
- LLM：OpenAI 兼容协议 BYO-Key；embedding 独立配置；核心 AI 拆 `outline_planner / tutor / quiz` 三个小 skill
- 当前导入仅 EPUB / TXT / PDF / Markdown 单文件；不做网页、GitHub、粘贴文本或补充资料

## 常用命令

> 当前仓库已按[决策记录](docs/v0.1/决策记录.md) #24 清零重写：backend / frontend 已删除，待按 v0.1 产品文档重建；以下命令在重建后生效。

```bash
cd backend  && uv sync && uv run uvicorn app.main:app --reload
cd frontend && pnpm install && pnpm dev
cd backend  && uv run pytest && uv run ruff check . && uv run mypy app
cd frontend && pnpm lint && pnpm tsc --noEmit
cd frontend && pnpm e2e
```

## 硬性约定

1. **需求驱动**：从 V0.1 需求 ID 出发；完成 = 验收逐条通过 + 测试绿 + 真实界面走查，不是“能跑就行”。
2. **防重复造轮子**：实现前检索 GitHub/官方文档有无成熟闭环方案，结论记入 commit。
3. **最小改动**：ponytail 精神——不写没人要的抽象与兜底；shortcut 用 `shortcut: <限制>, <何时升级>` 注释留痕。
4. **知识点是数据枢纽**：会话与测验通过 knowledge point 关联（后续候选的卡片与档案同样以它为枢纽）；检索切片不是学习单位。
5. **结构先于 AI**：目录识别零 LLM；目录规划未配置或失败必须保留原树，不阻塞基础学习路径。
6. **证据与数据不丢**：目录编辑不得静默删除会话、测验记录或点亮状态；点亮口径透明（当前通过 ≠ 长期记忆）。
7. **测试分层**：核心算法单测必测；LLM 一律 mock 不花真 token；E2E 验证真实闭环与回跳、重考等结果。
8. **API Key 安全**：加密落库，任何日志、导出与 LLM 请求不得含明文 key。
9. **范围克制**：计划、复习、卡片、掌握档案等后续候选内容，以及书籍分享、社区、账号、跨书统一档案与通用技能平台，均不在 V0.1。

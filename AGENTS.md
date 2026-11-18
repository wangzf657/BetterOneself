# BetterOneself

不限定领域的伴学 Agent:导入资料 → 拆解知识点 → 排计划 → 每天陪学、考练、督促复习,直到真的学会。V1.0 单机自用,跑通"导入→规划→学习→复习→督促"闭环。

## 文档是一等公民——动代码前先读文档

| 文档 | 内容 | 什么时候读 |
|---|---|---|
| [docs/00-产品总纲.md](docs/00-产品总纲.md) | 产品定义、概念模型、核心闭环、路线图 | 不确定"该不该做"时 |
| [docs/01-技术总纲.md](docs/01-技术总纲.md) | 技术选型、架构、代码规范、流程、测试 | 写任何代码前;改依赖/数据模型前看第 5.4 节 |
| [docs/v1.0/需求.md](docs/v1.0/需求.md) | 42 条需求与验收标准(ID: M1-01…) | 每个功能的完成定义;commit 引用需求 ID |
| [docs/v1.0/数据模型.md](docs/v1.0/数据模型.md) | 表结构、外键、指标口径 | 改任何 models/ 之前;字段增删先过 5.4 评审 |
| [docs/v1.0/页面清单.md](docs/v1.0/页面清单.md) | 路由、页面信息层级、交互约定 | 新增/改动页面或路由之前 |
| [docs/research/](docs/research/) | 竞品调研三份 | 找设计依据与参考项目 |

**文档与代码冲突时:先改文档(以评审后的新结论),再改代码。**

## 技术栈速览(详见技术总纲第 1 节)

- backend:Python 3.12 / FastAPI / SQLAlchemy 2 + SQLite(sqlite-vec)/ LangGraph / py-fsrs / Docling
- frontend:React 19 + Vite + TS strict / shadcn/ui + Tailwind 4 / TanStack Query
- LLM:OpenAI 兼容协议 BYO-Key;编排边界见技术总纲 2.3(不是所有 LLM 调用都上 LangGraph)

## 常用命令

```bash
cd backend  && uv sync && uv run uvicorn app.main:app --reload   # 后端开发
cd frontend && pnpm install && pnpm dev                            # 前端开发
cd backend  && uv run pytest && uv run ruff check .                # 后端测试与 lint
cd frontend && pnpm lint && pnpm tsc --noEmit                      # 前端检查
cd frontend && pnpm e2e                                             # E2E 主链路(里程碑收尾必跑)
```

## 硬性约定

1. **需求驱动**:功能从需求清单 ID 出发,完成 = 验收标准逐条通过 + 测试绿,不是"能跑就行"
2. **防重复造轮子**:实现前先检索 GitHub/官方文档有无成熟闭环方案,结论记入 commit
3. **最小改动**:ponytail 精神——不写没人要的抽象与兜底;shortcut 用 `shortcut: <限制>, <何时升级>` 注释留痕
4. **知识点是数据枢纽**:所有模块通过 knowledge point 关联,新表先看概念模型(总纲第 6 节)
5. **测试分层**:核心算法单测必测;LLM 一律 mock 不花真 token;E2E 主链路 = 闭环没断的唯一定义
6. **API Key 安全**:加密落库,任何日志与 LLM 请求不得含明文 key

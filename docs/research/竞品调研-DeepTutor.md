# 竞品调研：DeepTutor

> 调研对象：[HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) | 数据快照：2026-11-18
> 58.9k stars / 7.2k forks / Apache-2.0 / 2025-12-29 发布，曾登 GitHub Trending
> 信息来源：GitHub README、arXiv 论文 2604.26962、官网 deeptutor.info、官方文档站 docs.deeptutor.info、公开搜索

## 1. 产品定位

**一句话**：DeepTutor 是港大 HKUDS 开源的"Agent 原生"终身个性化 AI 家教/学习工作台——不是"围绕文档问答的笔记助手"（NotebookLM 模式），而是"围绕学习者成长的智能体系统"。

- 官方自述："DeepTutor: Lifelong Personalized Tutoring"；"an agent-native learning workspace"
- 论文定位：《DeepTutor: Towards Agentic Personalized Tutoring》(arXiv:2604.26962)——针对 LLM"缺乏对个体学习者的适应"、RAG"无法提供个性化引导式反馈"的痛点，提出"静态知识接地 + 动态学习者记忆"混合引擎
- 目标用户：自学者和大学生为主（K-12 通过 Learner/Guardian 家长监护账户覆盖）
- **与 NotebookLM 的核心差异**：① 深度研究（带引文的报告生成，可"越过知识库往外看"）；② 三层记忆系统跨会话认识学习者；③ 可通过 IM 渠道（15+）主动触达学习者
- 商业模式：README 明确声明无任何付费在线产品，纯开源 + 社区共建

## 2. 核心功能清单

| 功能 | 说明 | 成熟度 |
|---|---|---|
| Chat（智能体对话） | 单一 agent loop：调工具、接知识库、读附件、咨询子智能体；可选工具含 web_search/paper_search/reason 等 | 成熟 |
| 多引擎 RAG 知识库 | Knowledge Center：每个 KB 绑定一种检索引擎（LlamaIndex 默认/PageIndex/GraphRAG/WeKnora/Obsidian 库等）；GitHub 仓库/文档站定时同步；解析引擎可选 MinerU/Docling/Tika 等 | 成熟 |
| Deep Research | 带引文的研究报告；搜索服务商可插拔；部分结果如实标记 | 较成熟（有输出截断 issue） |
| **Mastery Path（掌握路径）** | 学习目标 → 知识点地图 → 逐站学习；按"评估出的掌握"推进而非阅读时长；知识点分 memory/procedure/concept/design 四类 | 较成熟 |
| Immersive Reading | 文档/网页/YouTube/Bilibili 在对话旁打开，逐页引文、批注、进度保存 | 较成熟 |
| Book（活书） | 资料编译成可交互"活书"：**章节大纲先经用户确认再生成**；类型化块（文本/测验/闪卡/时间线/代码/概念图）；导出 Markdown | 较成熟 |
| Practice + Question Bank | chat/book/mastery 产生的题自动入题库；每日到期复习队列（每组≤20 题）；错题次日回队 | 较成熟 |
| 间隔重复调度 | 四档回忆评分：Again/Hard/Mastered/Easy；优先过期题 | 较成熟（算法细节未公开） |
| Learning Notebook | 块编辑器笔记；选中段落唤起侧边讨论（解释/举例/改写/出题）；闪卡可导出 Anki | 较成熟 |
| Memory（三层记忆） | L1 事件轨迹 / L2 精选事实 / L3 跨域综合，全部文件化可读可编辑；Memory Graph 可视化证据链；"deliberately not a hidden vector store" | 较成熟 |
| Partners（IM 陪伴） | 账号级持久伴侣，SOUL.md 人格；接入飞书/Telegram/钉钉/企微等 15+ 渠道；支持多 Partner 群聊 | 较成熟 |
| Skills 生态（EduHub） | 开放 SKILL.md 格式；教育技能注册中心（苏格拉底导师、闪卡生成、作文批改等）；导入有安全门 | 较成熟 |
| Task Board / Calendar | 待办看板、日历（.ics 导出）、学习日志 | 较成熟 |
| 多用户/管理 | 默认单用户免登录；可开认证；Guardian 家长报告与材料审批 | 较成熟（配置复杂） |
| CLI/SDK | 单一二进制 REPL + NDJSON，可被其他 Agent 当工具驱动 | 较成熟 |
| 桌面端 | macOS/Windows 安装包，捆绑运行时免终端 | 预览（未签名） |
| 移动端原生 App | — | 未查到（仅 Web 移动布局） |

## 3. 用户使用流程

1. **安装初始化**：桌面包 / Docker / pip 任选；`deeptutor init` 向导配置端口与 LLM Provider（**前提：自备 API Key**）
2. **配置模型**：Settings 有 Readiness 矩阵给能力就绪度打分
3. **建工作区**：按学科/项目划分，各自隔离对话、学习活动与资料
4. **导入资料**：上传 PDF/DOCX/EPUB 等，或连 GitHub 仓库/文档站/YouTube/Bilibili；选解析与检索引擎，建索引
5. **日常对话**：带知识库提问获逐页引文；有用片段存 Favorites
6. **整理知识**：块编辑器笔记；对段落追问或生成练习题
7. **结构化学习活动**（四选一）：Book（大纲确认→活书编译→章内测验）/ Mastery Path（导师问先验与时间→共同设计知识点地图→逐站学习，**答对评估题才放行**）/ Immersive Reading / Practice
8. **复习循环**：每日到期队列 → 四档评分 → 错题次日回归
9. **个性化沉淀**：Memory 自动积累（L1→L2→L3），用户可审查编辑
10. **多端陪伴（可选）**：创建 Partner 绑定 IM 渠道，主动推送提问与提醒

## 4. 学习科学 / 教学法设计

| 机制 | 实现 | 对应原则 |
|---|---|---|
| 掌握度门控 | "assessed mastery gate controls progression"——由评估掌握（非阅读时长）控制推进；自评与评估分开记录 | Mastery learning |
| 知识点类型学 | 分 memory/procedure/concept/design 四类，类型决定"何种证据算掌握" | 知识分类学（近似 Bloom） |
| 主动回忆/生成效应 | "Reading an answer alone does not demonstrate a concept or design skill"——concept/design 卡要求学习者自己解释 | Retrieval practice |
| 间隔重复 | 四档评分更新到期日；错题次日回归 | Spaced repetition |
| 先验知识诊断 | 设计大纲前导师询问先验知识和可用时间 | 前测效应 |
| 难度校准出题 | 论文："difficulty-calibrated question generation" | Desirable difficulties |
| 苏格拉底式教学 | EduHub 显式提供 Socratic tutors 技能 | 苏格拉底提问法 |
| 元认知 | Learning Journal 记录已确认的学习记录 | 元认知监控 |

**值得注意的克制**：Anki 导出时明确说明不导出自己的复习排程；承认自评"不会变成独立评估的技能"。

**未查到**：间隔重复具体算法（SM-2/FSRS/自研）、学习科学文献引用、教学效果对照实验数据。

## 5. 产品架构的产品视角

**两个作用域 × 五个架层**：

- **Workspace（工作区）**：按学科划分，一个科目一个容器（资料/进度/对话不串味）
- **Account（账号）**：Partners（IM 伴侣）与 Personalization（人格/技能/记忆）跨工作区存在——"属于我这个人，不属于某个科目"

五个架层：
1. **一个 Agent Loop，多种学习模式**：Chat/Quiz/Research/Mastery Path 等都是同一对话引擎上的能力——核心赌注是"学习即对话 + 工具调用"
2. **知识层**：知识库 = 绑定检索引擎的文档集合，四种学习活动复用同一份知识；`kb eval` 把检索质量变成可量化问题
3. **记忆层**：L1→L2→L3 金字塔，文件化、带证据边、可编辑——个性化从黑盒变成用户资产
4. **行为层**：Persona/Skills/MCP/Partners——可扩展性的统一抽象
5. **渠道层**：Web/桌面/CLI/SDK/IM 同一运行时。"A Partner is a chat that has a personality and a phone number"

**与 NotebookLM 的架构观差异**：NotebookLM 中心概念是"笔记本=资料集"，人是被动提问者；DeepTutor 中心概念是"学习者=被服务的对象"，资料只是记忆与接地的输入之一。

## 6. 亮点与不足

**亮点**：
1. **记忆可审计**：三层记忆 + 证据图 + 可编辑——教育场景建立信任的关键设计
2. **生成前先确认大纲**：避免黑盒一次性输出；编译前给成本预估
3. **掌握度门控替代进度条**：自评与评估分开记录，诚实
4. **检索质量可评测**：`kb eval` 用 QA 集打分（Recall@k/nDCG@k），RAG 从玄学变工程
5. **诚实的 UX 细节**：截断可见化、部分报告标记、API Key 永不经模型之手
6. **Agent 原生双形态**：既是人的产品，也是其他 Agent 的工具
7. **开放生态**：Anki 导出、Obsidian 原地读写——承认用户已有工具链

**不足**：
1. **部署门槛高**：自托管 + 自配 API Key 是硬前提；版本迭代快到"需要锁 patch 版本才能稳定部署"
2. 快速迭代伴随核心流程回归（纯修复版本多个；Deep Research 有工具调用截断问题）
3. 安全信任：单机默认允许 AI 在本机沙盒执行自生成代码
4. 成本对新手不透明
5. **移动端缺位**：无原生 App——对"伴学"场景（碎片时间、随时提醒）是明显短板
6. 间隔重复算法不透明、无法调参，重度 SRS 用户仍被导向 Anki

## 7. 对我们的启示

1. **把"掌握度门控"作为学习闭环的中枢**：为每个知识点定义"掌握证据类型"，concept 类强制学习者用自己的话解释，自评与测评分开呈现
2. **个性化记忆做成"可审查的显性资产"**：从第一天按可导出、可审计、可删除设计
3. **生成式内容一律"大纲先行 + 成本预估前置"**：成为所有长内容生成（讲义/测验卷）的标准交互
4. **复习闭环"机制完整但生态开放"**：内置四档评分 + 到期队列 + 错题回归，同时提供 Anki 导出
5. **"深度工作在 Web，陪伴触达在 IM"的双渠道结构**：提醒复习、推错题走 IM；精讲、批改走 Web。可先选 1-2 个国内渠道做主动陪伴层

## 来源

- https://github.com/HKUDS/DeepTutor （README、版本历史）
- https://arxiv.org/abs/2604.26962 （论文）
- https://deeptutor.info/ 、https://docs.deeptutor.info/ （官网与文档站，含 Mastery Path / Practice 页）
- 腾讯云开发者社区《DeepTutor 工程视角》（部署需锁版本）、GitHub Issues（token 截断问题）

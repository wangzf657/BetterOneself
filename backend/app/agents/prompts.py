"""提示词集中地。任务标记(__TASK__*)是 stub 与真实模型共同的契约,勿改。"""

import json

DECOMPOSE_SYSTEM = """__TASK__KNOWLEDGE_EXTRACT__
你是知识点拆解引擎。从资料切片中抽取可独立学习的最小知识点。

资料切片在 ```chunks JSON 块中给出,每项含 chunk_id / heading_path / content。
输出 JSON:
{"kps": [{"name": str, "summary": str,
          "kp_type": "concept"|"fact"|"procedure", "refs": [chunk_id]}]}

规则:
- name:简明确的知识点名,不要用整章标题
- summary:一两句话说明学与不学的边界
- kp_type:概念=concept,事实=fact,操作/步骤=procedure
- refs:支撑该知识点的切片 id,必须来自给定 chunk_id;确无来源支撑时才允许空数组
- 粒度克制:一段正文通常 0-2 个知识点,不逐句拆
- 只输出 JSON,不解释"""


def decompose_messages(batch: list[dict]) -> list[dict]:
    payload = "```chunks\n" + json.dumps(batch, ensure_ascii=False) + "\n```"
    return [
        {"role": "system", "content": DECOMPOSE_SYSTEM},
        {"role": "user", "content": payload},
    ]


LECTURE_SYSTEM_GUIDED = """__TASK__LECTURE__
你是伴学讲解导师,当前处于苏格拉底引导模式:
- 先引导学习者自己思考:抛回问题、给分层提示(从方向到方法到关键事实),不直接给完整答案
- 学习者明确索要答案时,先给一层更具体的提示并说明"最后一步留给你"
- 学习者连续两次卡住或明确放弃,才给完整讲解
- concept 类内容在收尾时要求学习者用自己的话复述

引用规则(两种模式一致):
- 回答中凡依据资料的内容,在句末标注来源编号 [n];n 对应提供的资料切片编号
- 优先依据切片内容讲解;资料未覆盖的部分如实说明"资料中未提及"
- 分段呈现,单次回答聚焦一个小节(认知负荷控制)
- 全程中文"""

LECTURE_SYSTEM_DIRECT = """__TASK__LECTURE__
你是伴学讲解导师,当前处于直答模式:清晰、直接地讲解,不绕弯。
引用规则:
- 回答中凡依据资料的内容,在句末标注来源编号 [n];n 对应提供的资料切片编号
- 优先依据切片内容讲解;资料未覆盖的部分如实说明"资料中未提及"
- 分段呈现,单次回答聚焦一个小节(认知负荷控制)
- 全程中文"""

FEYNMAN_SYSTEM = """__TASK__FEYNMAN__
你是费曼技巧陪练:学习者用自己的话解释知识点,你负责挑错与追问。
回复结构:
1. 先确认解释中正确的部分(一句话)
2. 指出错误或遗漏(如有);解释基本正确时明确说"解释正确"
3. 以至少一个追问结尾——追问引导学习者补全、修正或延伸(M3-07 验收硬约束)
引用规则:
- 依据资料的内容标注来源编号 [n];n 对应提供的资料切片编号
- 全程中文"""


def lecture_messages(
    query: str,
    chunks: list[dict],
    history: list[dict],
    socratic: bool,
    session_type: str = "lecture",
) -> list[dict]:
    if session_type == "feynman":
        system = FEYNMAN_SYSTEM
        prefix = "学习者对知识点的解释:"
    else:
        system = LECTURE_SYSTEM_GUIDED if socratic else LECTURE_SYSTEM_DIRECT
        prefix = "学习者的问题:"
    numbered = [
        {"n": i + 1, "chunk_id": c["chunk_id"], "heading_path": c["heading_path"],
         "content": c["content"]}
        for i, c in enumerate(chunks)
    ]
    payload = (
        "```chunks\n" + json.dumps(numbered, ensure_ascii=False) + "\n```\n\n"
        f"{prefix}{query}"
    )
    return [
        {"role": "system", "content": system},
        *history,
        {"role": "user", "content": payload},
    ]


QUIZ_GEN_SYSTEM = """__TASK__QUIZ_GEN__
你是出题引擎。依据资料切片为知识点出 3 道测验题:2 道客观单选(objective)+ 1 道简答(short_answer)。
输出 JSON:{"quizzes": [{"q_type": "objective"|"short_answer", "question": str,
"options": [四个选项], "answer": str, "chunk_id": int}]}
规则:
- 客观题 answer 必须是 options 之一的原文;简答题 options 为空数组
- 题目必须能仅凭给定切片内容作答;考查理解而非原文背诵
- chunk_id 指向题目依据的切片
- 只输出 JSON"""


def quiz_gen_messages(kp_name: str, chunks: list[dict]) -> list[dict]:
    payload = (
        f"知识点:{kp_name}\n```chunks\n"
        + json.dumps(chunks, ensure_ascii=False)
        + "\n```"
    )
    return [
        {"role": "system", "content": QUIZ_GEN_SYSTEM},
        {"role": "user", "content": payload},
    ]


QUIZ_GRADE_SYSTEM = """__TASK__QUIZ_GRADE__
你是简答判分器。对照参考答案评判学习者作答,输出 JSON:{"is_correct": bool, "feedback": str}
规则:
- 判分从宽:核心概念正确、无关键性错误即 is_correct=true;表述差异不扣分
- feedback 一两句:对在哪里/缺了什么;答错时指出该回到哪个点
- 只输出 JSON"""


def quiz_grade_messages(question: str, reference: str, user_answer: str) -> list[dict]:
    payload = (
        "```quiz\n"
        + json.dumps(
            {"question": question, "reference": reference, "answer": user_answer},
            ensure_ascii=False,
        )
        + "\n```"
    )
    return [
        {"role": "system", "content": QUIZ_GRADE_SYSTEM},
        {"role": "user", "content": payload},
    ]


DEPS_SYSTEM = """__TASK__DEPS_INFER__
你是知识点依赖推断引擎。给定知识点列表,推断学习顺序上的前后依赖:A 依赖 B = 必须先学 B 才能理解 A。
输出 JSON:{"edges": [{"kp": "A 名称", "depends_on": "B 名称"}]}
规则:
- 只输出有把握的依赖;没有依赖关系的不要硬造
- 不要自环(A 依赖 A);名称必须来自给定列表原文
- 典型依赖:概念依赖它的前提概念;操作依赖相关概念;章节默认顺序仅供参考,不可无脑全链
- 只输出 JSON"""


def deps_messages(kps: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": DEPS_SYSTEM},
        {
            "role": "user",
            "content": "```kps\n"
            + json.dumps(kps, ensure_ascii=False)
            + "\n```",
        },
    ]

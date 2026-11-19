"""讲解会话(LangGraph,技术总纲 2.3):带引用生成,token 级流式。

shortcut: 会话历史以 messages 表为事实源、逐轮重建上下文,未接 LangGraph checkpointer;
M2 测验多步状态机出现"图中间挂起恢复"需求时再引 SqliteSaver
"""

import re
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.agents import llm, prompts

_CITE = re.compile(r"\[([1-9]\d{0,2})\]")


class LectureState(TypedDict, total=False):
    messages: list[dict]  # 装配完成的 LLM 消息
    chunks: list[dict]  # 编号后的上下文切片
    socratic: bool


def generate_node(state: LectureState) -> dict[str, Any]:
    writer = get_stream_writer()
    for piece in llm.chat_stream(state["messages"], temperature=0.4):
        writer({"type": "delta", "text": piece})
    return {}


def build_graph():
    graph = StateGraph(LectureState)
    graph.add_node("generate", generate_node)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    return graph.compile()


_graph = None


def stream_lecture(
    chunks: list[dict],
    history: list[dict],
    query: str,
    socratic: bool,
    session_type: str = "lecture",
):
    """执行一轮讲解,逐 token yield;调用方累积得完整回答。chunks 已按优先级排好。"""
    global _graph
    if _graph is None:
        _graph = build_graph()
    messages = prompts.lecture_messages(query, chunks, history, socratic, session_type)
    events = _graph.stream(
        {"messages": messages, "chunks": chunks, "socratic": socratic},
        {"configurable": {"thread_id": "lecture"}},
        stream_mode="custom",
    )
    for event in events:
        if event.get("type") == "delta":
            yield event["text"]


def extract_citations(answer: str, chunks: list[dict]) -> list[dict]:
    """从回答中的 [n] 标注提取被引用切片,保序去重,带定位信息。"""
    seen: set[int] = set()
    result: list[dict] = []
    for m in _CITE.finditer(answer):
        n = int(m.group(1))
        if 1 <= n <= len(chunks) and n not in seen:
            seen.add(n)
            c = chunks[n - 1]
            result.append(
                {
                    "index": n,
                    "chunk_id": c["chunk_id"],
                    "heading_path": c.get("heading_path", ""),
                    "source_id": c.get("source_id"),
                }
            )
    return result

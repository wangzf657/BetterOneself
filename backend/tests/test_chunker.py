"""切片器:标题边界、段落累积、heading_path 与行号。"""

from app.ingest.chunker import chunk_markdown


def test_split_on_h1_h2_and_keep_heading_path():
    md = "\n".join([
        "# Rust 基础",
        "所有权简介。",
        "## 移动语义",
        "赋值后原变量不可用。",
        "### 细节",
        "Drop 顺序。",
    ])
    chunks = chunk_markdown(md)
    assert [c.heading_path for c in chunks] == [
        "Rust 基础",
        "Rust 基础 > 移动语义",
    ]
    # 三级标题留在二级块内
    assert "### 细节" in chunks[-1].content


def test_accumulate_paragraphs_up_to_max_chars():
    para = "很长的段落。" * 300
    md = "# 标题\n" + para
    chunks = chunk_markdown(md, max_chars=500)
    assert len(chunks) > 1
    assert all(len(c.content) < 600 for c in chunks)
    assert all(c.heading_path == "标题" for c in chunks)


def test_line_numbers():
    md = "# A\n第一段。\n\n# B\n第二段。"
    chunks = chunk_markdown(md)
    assert chunks[0].start_line == 1
    assert chunks[1].start_line == 4


def test_empty_and_blank():
    assert chunk_markdown("") == []
    assert chunk_markdown("\n\n  \n") == []

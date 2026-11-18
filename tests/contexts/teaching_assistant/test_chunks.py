from contexts.teaching_assistant.domain.chunks import (
    SCORE_THRESHOLD,
    build_chunks,
    chunk_markdown,
    make_chunk_id,
)


def test_chunk_markdown_builds_heading_path_and_source_ref():
    md = "## 2.1 变量\n变量用于存储数据。\n## 2.2 循环\n循环结构用于重复执行。"
    pieces = chunk_markdown(md, "第2章 控制流程")
    assert pieces[0]["heading_path"] == "第2章 控制流程 > 2.1 变量"
    assert pieces[0]["source_ref"] == "2.1 变量"
    assert "变量用于存储数据" in pieces[0]["text"]


def test_chunk_markdown_no_heading_falls_back_to_title():
    pieces = chunk_markdown("这是一段没有标题的正文。", "第1章 绪论")
    assert pieces[0]["heading_path"] == "第1章 绪论"
    assert pieces[0]["source_ref"] == "第1章 绪论"


def test_chunk_markdown_empty_content_returns_empty():
    assert chunk_markdown("", "标题") == []
    assert chunk_markdown("   \n  ", "标题") == []


def test_chunk_markdown_splits_long_section():
    body = "。" * 2000
    pieces = chunk_markdown(body, "长章节")
    assert len(pieces) >= 3
    assert all(len(p["text"]) <= 800 for p in pieces)


def test_make_chunk_id_is_deterministic():
    assert make_chunk_id("c1", "第2章 > 2.1", 0) == make_chunk_id("c1", "第2章 > 2.1", 0)
    assert make_chunk_id("c1", "第2章 > 2.1", 0) != make_chunk_id("c1", "第2章 > 2.1", 1)


def test_build_chunks_none_or_empty_content_returns_empty():
    assert build_chunks("c1", "course1", "标题", None) == []
    assert build_chunks("c1", "course1", "标题", "") == []


def test_build_chunks_assembles_full_chunk():
    chunks = build_chunks("c1", "course1", "第2章 控制流程", "## 2.1 变量\n变量说明。")
    assert len(chunks) == 1
    c = chunks[0]
    assert c.chunk_id.startswith("chunk_")
    assert c.chapter_id == "c1"
    assert c.course_id == "course1"
    assert c.heading_path == "第2章 控制流程 > 2.1 变量"

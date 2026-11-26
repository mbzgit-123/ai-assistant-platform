from contexts.teaching_assistant.domain.chunks import (
    chunk_markdown_file,
    chunk_markdown_structured,
)


def test_structured_chunks_heading_path_and_chapter():
    md = "## 1.1 背景\n背景内容\n## 1.2 目标\n目标内容"
    recs = chunk_markdown_structured("doc1", "第1章 概述", md)
    assert [r["chapter"] for r in recs] == ["第1章 概述", "第1章 概述"]
    assert [r["heading_path"] for r in recs] == [
        ["第1章 概述", "1.1 背景"],
        ["第1章 概述", "1.2 目标"],
    ]
    assert [r["content"] for r in recs] == ["背景内容", "目标内容"]


def test_structured_chunks_nested_headings_build_path():
    md = "## 1.1 背景\n### 1.1.1 细节\n正文"
    recs = chunk_markdown_structured("doc1", "第1章", md)
    assert len(recs) == 1
    assert recs[0]["heading_path"] == ["第1章", "1.1 背景", "1.1.1 细节"]


def test_structured_chunks_no_inner_heading():
    recs = chunk_markdown_structured("doc1", "第1章 概述", "纯正文")
    assert len(recs) == 1
    assert recs[0]["heading_path"] == ["第1章 概述"]
    assert recs[0]["chapter"] == "第1章 概述"
    assert recs[0]["document_name"] == "doc1"


def test_structured_chunks_empty_content_returns_none():
    assert chunk_markdown_structured("doc1", "c", None) == []
    assert chunk_markdown_structured("doc1", "c", "  \n  ") == []


def test_structured_chunks_long_splits_with_overlap_and_index():
    md = "字" * 2500
    recs = chunk_markdown_structured("doc1", "第1章", md)
    assert len(recs) == 4  # MAX_CHUNK_CHARS=800, OVERLAP=50: 0/750/1500/2250
    assert [r["chunk_index"] for r in recs] == [0, 1, 2, 3]
    assert all(r["total_chunks"] == 4 for r in recs)
    # 重叠：第二片开头 == 第一片结尾 50 字符
    assert recs[1]["content"].startswith(recs[0]["content"][-50:])


def test_structured_chunks_ids_stable_and_unique():
    recs = chunk_markdown_structured("doc1", "第1章", "a" * 1500)
    ids = [r["id"] for r in recs]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("chunk_") for i in ids)
    recs2 = chunk_markdown_structured("doc1", "第1章", "a" * 1500)
    assert [r["id"] for r in recs2] == ids


def test_file_chunking_h1_becomes_chapter():
    md = "# 第一章\n正文A\n# 第二章\n正文B"
    recs = chunk_markdown_file("课程.md", md)
    assert [r["chapter"] for r in recs] == ["第一章", "第二章"]
    assert [r["heading_path"] for r in recs] == [["第一章"], ["第二章"]]
    assert [r["document_name"] for r in recs] == ["课程.md", "课程.md"]


def test_file_chunking_content_before_first_heading_falls_back():
    md = "前言内容\n# 第一章\n正文"
    recs = chunk_markdown_file("课程.md", md)
    assert recs[0]["heading_path"] == ["课程.md"]
    assert recs[0]["chapter"] == "课程.md"
    assert recs[1]["heading_path"] == ["第一章"]


def test_file_chunking_nested_headings_build_path():
    md = "# 第一章\n## 1.1 背景\n正文"
    recs = chunk_markdown_file("课程.md", md)
    assert recs[0]["heading_path"] == ["第一章", "1.1 背景"]
    assert recs[0]["chapter"] == "第一章"


def test_code_fence_hash_lines_not_treated_as_headings():
    md = "## 环境配置\n```\n# 安装依赖\nimport os\n```\n后面正文"
    recs = chunk_markdown_file("课程.md", md)
    paths = [r["heading_path"] for r in recs]
    assert all("安装依赖" not in p for p in paths)
    assert paths[0] == ["环境配置"]
    assert "import os" in recs[0]["content"]


def test_chunk_cleans_separator_and_blank_lines():
    md = "## 说明\n正文A\n\n\n\n正文B\n```\n# =========================\nimport os\n# -------------------------\nprint(1)\n```"
    recs = chunk_markdown_file("课程.md", md)
    content = recs[0]["content"]
    assert "====" not in content
    assert "----" not in content
    assert "import os" in content
    assert "print(1)" in content
    assert "\n\n\n" not in content


def test_chunk_unescapes_backslashes():
    md = r"## 说明" + "\n" + r"尺寸 32 \* 7 \* 7"
    recs = chunk_markdown_file("课程.md", md)
    assert r"\*" not in recs[0]["content"]
    assert "32 * 7 * 7" in recs[0]["content"]


def test_chunk_strips_blockquote_markers():
    md = "## 说明\n> 这是引用内容\n    > 缩进引用\n正文"
    recs = chunk_markdown_file("课程.md", md)
    content = recs[0]["content"]
    assert "> 这是引用" not in content
    assert "> 缩进引用" not in content
    assert "这是引用内容" in content
    assert "缩进引用" in content

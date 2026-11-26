# teaching_assistant Markdown 切片程序设计（2026-11-26）

## 意图

teaching_assistant 现有检索链：`Chapter.content_md`（Word 转 Markdown 后落库，表格/图片已转文本）→ `chunk_markdown`（按 `#` 标题切 + 长度 + 重叠）→ `HashEmbedding` + `InMemoryVectorStore`。

本阶段**在现有 `content_md` 上做结构化切片**，产出符合需求 2.3 的 JSON 记录，作为后续接 Milvus + BGE-M3 的原料。**不重新解析 Word**（md 已处理过表格/图片），**不接向量库、不接 BGE-M3、不改现有 markdown 检索路径。**

## 目标 / 非目标 / 反目标

- 目标：新增纯函数 `chunk_markdown_structured`，对 `content_md` 做三层切片，产出 `heading_path[]` 数组 + `chapter`/`document_name`/`chunk_index`/`total_chunks`。
- 非目标：Milvus 落库、BGE-M3 嵌入、python-docx 解析、改现有 `chunk_markdown`/`Chunk`/内存检索路径。
- 反目标：不做图片 OCR；不破坏现有 233 个测试。

## 约束

- contexts 间禁止互相 import；纯切片逻辑放 `domain/chunks.py`。
- 复用现有 `_HEADING_RE`、`_split_text`（长度 800 + 重叠 50，满足 800–1200 区间）、sha1 短 id 思路。
- **新增函数，不改旧 `chunk_markdown`/`build_chunks`**（避免影响内存检索路径）。

## 方案

在 `contexts/teaching_assistant/domain/chunks.py` 新增：

1. `_group_sections(chapter, content_md) -> list[tuple[list[str], str]]`：按 `#` 标题层级归组，返回 `(heading_path 数组, 正文文本)`。`heading_path[0]` 恒为 `chapter`。
2. `chunk_markdown_structured(document_name, chapter, content_md) -> list[dict]`：三层切片（标题层级 → `_split_text` 长度控制 → 重叠），产出记录。
3. `make_chunk_record_id(document_name, heading_path, chunk_index) -> str`：sha1 短 id。

外加 `infrastructure/build_chunks.py`：读 `Chapter` 表 → 逐章切片 → 写 `data/chunks.jsonl`（每行一条，`ensure_ascii=False`）。

## 产出 Schema（对齐需求 2.3）

```json
{
  "id": "chunk_<sha1前12>",
  "document_name": "doc1",
  "chapter": "第1章 概述",
  "heading_path": ["第1章 概述", "1.1 背景"],
  "content": "切片文本",
  "chunk_index": 0,
  "total_chunks": 3
}
```

- `document_name` = `Chapter.document_id`（空则回退 `Chapter.title`）。
- `chapter` = `Chapter.title`。
- `heading_path` = `[chapter] + 内层 # 标题`；无内层标题时为 `[chapter]`。
- `chunk_index` / `total_chunks` = **按 chapter 计**（本函数每次只处理一章）。

## 决策（我的 call）

- `document_name` 用 `document_id`（当前 Chapter 表无文档名，只有 `document_id`；后续有真实文档名可换）。
- 切片长度沿用现有 `MAX_CHUNK_CHARS=800`、重叠 `OVERLAP_CHARS=50`（在需求 800–1200 区间内）。

## 留给后续（本阶段不做）

- BGE-M3 嵌入（复用 `sales_assistant.infrastructure.embeddings.create_embeddings`）。
- Milvus 落库（复用 `sales_assistant.infrastructure.knowledge_base` 的 hybrid 索引范式）。
- 替换现有 `HashEmbedding + InMemoryVectorStore` 路径。

import hashlib
import re
from dataclasses import dataclass

MAX_CHUNK_CHARS = 800
OVERLAP_CHARS = 50

# BGE-M3 dense IP 相似度阈值（实测校准：相关查询 top-1 ≥ 0.57，无关查询 ≤ 0.50）
SCORE_THRESHOLD: float = 0.55

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class RetrievedChunk:
    """Milvus 检索返回的课件切片命中结果。"""

    chunk_id: str
    document_name: str
    chapter: str
    heading_path: str
    text: str
    score: float


def _split_text(text: str) -> list[str]:
    """按 MAX_CHUNK_CHARS 滑动切分正文，OVERLAP_CHARS 重叠；跳过空白。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        pieces.append(text[start:end])
        if end >= len(text):
            break
        start = end - OVERLAP_CHARS
    return pieces


_SEPARATOR_CHARS = set("-=*_")


def _is_separator(line: str) -> bool:
    """判断是否为纯分隔线（# ==== / # ---- / --- / ==== 等）。"""
    s = line.strip()
    if s.startswith("#"):
        s = s[1:].strip()
    return len(s) >= 3 and all(c in _SEPARATOR_CHARS for c in s)


def _strip_blockquote(line: str) -> str:
    """去掉 Word→md 转换残留的引用标记（行首 > 及其后可选空格）。"""
    stripped = line.lstrip()
    while stripped.startswith(">"):
        stripped = stripped[1:].lstrip()
    return stripped


def _clean_text(text: str) -> str:
    """清理 Word→md 转换噪声：去分隔线/引用标记、合并连续空行、反转义常见转义符。"""
    out: list[str] = []
    blank_run = 0
    for raw in text.split("\n"):
        line = raw.rstrip()
        if _is_separator(line):
            continue
        line = _strip_blockquote(line)
        line = line.replace(r"\*", "*").replace(r"\_", "_").replace(r"\#", "#").replace(r"\`", "`")
        if not line.strip():
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        out.append(line)
    return "\n".join(out).strip()


def _group_sections(
    content_md: str,
    base: list[str] | None = None,
) -> list[tuple[list[str], str]]:
    """按 Markdown 标题层级归组，返回 (heading_path 数组, 正文文本)。

    base 若给定则作为 heading_path 的前缀（如 DB 场景注入 chapter）；否则 heading_path
    完全由正文内标题决定。代码围栏（```）内的 `#` 行不当作标题。
    """
    sections: list[tuple[list[str], str]] = []
    stack: list[tuple[int, str]] = []
    body_lines: list[str] = []
    in_code = False

    def heading_path() -> list[str]:
        return (base or []) + [label for _, label in stack]

    def flush() -> None:
        text = _clean_text("\n".join(body_lines))
        body_lines.clear()
        if text:
            sections.append((heading_path(), text))

    for line in content_md.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            body_lines.append(line)
            continue
        if not in_code:
            m = _HEADING_RE.match(line)
            if m:
                flush()
                level = len(m.group(1))
                label = m.group(2).strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, label))
                continue
        body_lines.append(line)

    flush()
    return sections


def make_chunk_record_id(document_name: str, heading_path: list[str], chunk_index: int) -> str:
    key = "|".join([document_name, *heading_path, str(chunk_index)])
    return "chunk_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _to_records(document_name: str, pieces: list[dict]) -> list[dict]:
    total = len(pieces)
    return [
        {
            "id": make_chunk_record_id(document_name, p["heading_path"], i),
            "document_name": document_name,
            "chapter": p["heading_path"][0],
            "heading_path": p["heading_path"],
            "content": p["content"],
            "chunk_index": i,
            "total_chunks": total,
        }
        for i, p in enumerate(pieces)
    ]


def chunk_markdown_structured(
    document_name: str,
    chapter: str,
    content_md: str | None,
) -> list[dict]:
    """三层切片：标题层级 → 长度控制 → 重叠，产出结构化记录。

    每条记录含 heading_path 数组 + document_name/chapter/chunk_index/total_chunks。
    chapter 作为 heading_path[0]（DB 场景：chapter 存于 Chapter.title，正文只有 ## 子标题）。
    """
    if not content_md or not content_md.strip():
        return []
    pieces: list[dict] = []
    for heading_path, text in _group_sections(content_md, base=[chapter]):
        for piece in _split_text(text):
            pieces.append({"heading_path": heading_path, "content": piece})
    return _to_records(document_name, pieces)


def chunk_markdown_file(document_name: str, content_md: str | None) -> list[dict]:
    """对整份 md 文件切片（文件场景：文件名 = document_name，正文内 # 标题即章节）。

    无标题的前置内容回退为 heading_path = [document_name]；chunk_index/total_chunks 按整份文档计。
    """
    if not content_md or not content_md.strip():
        return []
    pieces: list[dict] = []
    for heading_path, text in _group_sections(content_md):
        hp = heading_path or [document_name]
        for piece in _split_text(text):
            pieces.append({"heading_path": hp, "content": piece})
    return _to_records(document_name, pieces)

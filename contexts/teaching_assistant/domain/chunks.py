import hashlib
import re
from dataclasses import dataclass

MAX_CHUNK_CHARS = 800
OVERLAP_CHARS = 50

SCORE_THRESHOLD: float = 0.3
HANDOFF_KEYWORDS: tuple[str, ...] = ("转人工", "找老师", "人工客服")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class Chunk:
    chunk_id: str
    chapter_id: str
    course_id: str
    text: str
    heading_path: str
    source_ref: str


@dataclass
class ScoredChunk:
    chunk: Chunk
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


def chunk_markdown(content_md: str, title: str) -> list[dict]:
    """按 Markdown 标题层级切分正文，保留标题上下文。

    返回 list[dict]，每个 dict 含 text / heading_path / source_ref 三键。
    """
    if not content_md or not content_md.strip():
        return []

    pieces: list[dict] = []
    stack: list[tuple[int, str]] = []
    body_lines: list[str] = []

    def heading_path() -> str:
        if not stack:
            return title
        return title + " > " + " > ".join(label for _, label in stack)

    def source_ref() -> str:
        if not stack:
            return title
        return stack[-1][1]

    def flush() -> None:
        text = "\n".join(body_lines)
        body_lines.clear()
        if not text.strip():
            return
        hp = heading_path()
        sr = source_ref()
        for piece in _split_text(text):
            pieces.append({"text": piece, "heading_path": hp, "source_ref": sr})

    for line in content_md.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            label = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, label))
        else:
            body_lines.append(line)

    flush()
    return pieces


def make_chunk_id(chapter_id: str, heading_path: str, index: int) -> str:
    digest = hashlib.sha1(f"{chapter_id}|{heading_path}|{index}".encode("utf-8")).hexdigest()[:12]
    return "chunk_" + digest


def build_chunks(
    chapter_id: str,
    course_id: str | None,
    title: str,
    content_md: str | None,
) -> list[Chunk]:
    if content_md is None or not content_md.strip():
        return []
    return [
        Chunk(
            chunk_id=make_chunk_id(chapter_id, piece["heading_path"], i),
            chapter_id=chapter_id,
            course_id=course_id or "",
            text=piece["text"],
            heading_path=piece["heading_path"],
            source_ref=piece["source_ref"],
        )
        for i, piece in enumerate(chunk_markdown(content_md, title))
    ]

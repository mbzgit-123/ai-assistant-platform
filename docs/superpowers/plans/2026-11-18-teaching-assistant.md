# 助教 Agent（teaching_assistant）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 FR-008 课后答疑：学员提问 → 检索课件分块 → LLM 生成可溯源讲解；低置信度或明确要求时转授课老师。

**Architecture:** 纯 Service + 端口（不引 LangGraph / 真实 Milvus）。领域层放 `Chunk`/`ScoredChunk` 数据类与 `chunk_markdown` 纯函数；`HashEmbedding`（确定性 n-gram 哈希向量）+ `InMemoryVectorStore`（余弦 Top-K）+ `StubHandoff` 均为内存/stub 实现；接口层收进 `contexts/teaching_assistant/interface/`。

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy 2.x / Pydantic v2 / structlog / pytest（内存 SQLite + 确定性 embedding + FakeLLM，零外部依赖）。

**Spec:** `docs/superpowers/specs/2026-11-18-teaching-assistant-design.md`

## Global Constraints

- 依赖方向：`contexts/teaching_assistant` 只依赖 `shared` + 自身；不依赖 `api/`。
- LLM 仅走 `LLMPort.chat(messages: list[dict[str,str]]) -> LLMResult`，用 `result.content`（纯文本）；无 JSON mode、无工具调用。
- 不新增数据库表、不新增第三方依赖；复用 `Chapter`（`shared.infrastructure.db.models.sync_cache`）。
- 统一响应信封 `ok(data=..., trace_id=get_trace_id())` 来自 `shared.infrastructure.web.response`。
- 领域接口（路由/请求模型/装配）一律放 `contexts/teaching_assistant/interface/`，不在外部 `api/`。
- 测试零外部依赖：内存 SQLite（StaticPool）、`FakeLLMAdapter`、确定性 `HashEmbedding`。

## Review Focus

以下输入类/失败模式由 spec 隐含、但单个任务的测试容易漏掉，逐一加测试钉死：

1. **空/空白问题** → 应转人工（`handoff=True`），不调 LLM、不抛异常。（Task 5）
2. **空向量库（无任何分块索引）** → `search` 返回 `[]`，服务按未命中转人工，`max()` 不抛异常。（Task 3、Task 5）
3. **`content_md = None` / 空** → `build_chunks` 返回 `[]`，不崩溃。（Task 1）
4. **embedding 确定性** → 同一文本在不同 `HashEmbedding` 实例上向量一致（禁 Python 内置 `hash()` 随机化）。（Task 2）
5. **低分分块** → `score < 0.3` 的分块虽在 top_k 内，也不进入 `sources` 与 LLM prompt。（Task 5）
6. **零向量余弦** → 空问题向量与分块向量求余弦返回 0，不除零。（Task 3）

---

### Task 1: 领域类型 + 分块纯函数

**Files:**
- Create: `contexts/teaching_assistant/domain/__init__.py`
- Create: `contexts/teaching_assistant/domain/chunks.py`
- Create: `contexts/teaching_assistant/domain/ports.py`
- Test: `tests/contexts/teaching_assistant/test_chunks.py`

**Interfaces:**
- Consumes: 无（首个任务）。
- Produces:
  - `Chunk`（dataclass）：`chunk_id: str, chapter_id: str, course_id: str, text: str, heading_path: str, source_ref: str`
  - `ScoredChunk`（dataclass）：`chunk: Chunk, score: float`
  - `SCORE_THRESHOLD: float = 0.3`
  - `HANDOFF_KEYWORDS: tuple[str, ...] = ("转人工", "找老师", "人工客服")`
  - `chunk_markdown(content_md: str, title: str) -> list[dict]`（dict 键：`text`/`heading_path`/`source_ref`）
  - `make_chunk_id(chapter_id: str, heading_path: str, index: int) -> str`
  - `build_chunks(chapter_id: str, course_id: str | None, title: str, content_md: str | None) -> list[Chunk]`
  - `EmbeddingPort`（Protocol）：`embed(text: str) -> list[float]`
  - `VectorStorePort`（Protocol）：`upsert(chunks: list[Chunk]) -> None`；`search(embedding: list[float], top_k: int) -> list[ScoredChunk]`
  - `HandoffPort`（Protocol）：`create_handoff(question: str, student_id: str | None) -> str`

- [ ] **Step 1: 写失败测试** `tests/contexts/teaching_assistant/test_chunks.py`

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_chunks.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.teaching_assistant.domain'`）

- [ ] **Step 3: 实现 `chunks.py` 与 `ports.py`**

`chunks.py` 分块算法（钉死）：
- 标题行匹配 `^(#{1,6})\s+(.+)$`；标题层级 = `#` 数量。
- 维护标题栈 `[(level, label)]`：遇到新标题，弹出 `level >= 新level` 的栈顶，再压入；当前 `heading_path = title + " > " + " > ".join(各层label)`（无标题则 `= title`）；`source_ref` = 最内层标题 label（无则 `title`）。
- 每个标题段内正文按 `MAX_CHUNK_CHARS = 800` 滑动切分，`OVERLAP_CHARS = 50` 重叠；跳过空白块。
- `make_chunk_id` 用 `hashlib.sha1(f"{chapter_id}|{heading_path}|{index}".encode("utf-8")).hexdigest()[:12]`，前缀 `"chunk_"`。
- `build_chunks`：`content_md` 为 None/空白 → `[]`；否则 `chunk_markdown` 后用 `make_chunk_id(chapter_id, heading_path, i)` 组装 `Chunk`（`course_id or ""`）。

`ports.py` 三个 Protocol（`VectorStorePort` 从 `chunks` 导入 `Chunk`/`ScoredChunk`）。

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_chunks.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/teaching_assistant/domain tests/contexts/teaching_assistant/test_chunks.py
git commit -m "feat: add teaching assistant domain chunks and ports"
```

---

### Task 2: HashEmbedding（确定性哈希向量）

**Files:**
- Create: `contexts/teaching_assistant/infrastructure/__init__.py`
- Create: `contexts/teaching_assistant/infrastructure/embedding.py`
- Test: `tests/contexts/teaching_assistant/test_embedding.py`

**Interfaces:**
- Consumes: Task 1 的 `EmbeddingPort`。
- Produces: `HashEmbedding`（`__init__(self, dim: int = 256)`、`embed(text: str) -> list[float]`，实现 `EmbeddingPort`）。

- [ ] **Step 1: 写失败测试** `tests/contexts/teaching_assistant/test_embedding.py`

```python
import math

from contexts.teaching_assistant.infrastructure.embedding import HashEmbedding


def test_embed_is_deterministic_across_instances():
    a = HashEmbedding().embed("什么是循环结构")
    b = HashEmbedding().embed("什么是循环结构")
    assert a == b


def test_embed_has_fixed_dim_and_non_negative():
    v = HashEmbedding(dim=256).embed("循环结构")
    assert len(v) == 256
    assert all(x >= 0 for x in v)


def test_embed_is_l2_normalized():
    v = HashEmbedding().embed("循环结构用于重复执行一段代码")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-9


def test_embed_empty_returns_zero_vector():
    v = HashEmbedding(dim=256).embed("")
    assert v == [0.0] * 256
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_embedding.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.teaching_assistant.infrastructure'`）

- [ ] **Step 3: 实现 `HashEmbedding`**

字符 2-gram 与 3-gram 哈希计数，**非负**、固定维度、L2 归一化。哈希用 `hashlib.md5(gram.encode("utf-8")).digest()` 转 `int` 取模——**禁用 Python 内置 `hash()`**（进程级随机）。空文本返回零向量。

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_embedding.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/teaching_assistant/infrastructure/embedding.py contexts/teaching_assistant/infrastructure/__init__.py tests/contexts/teaching_assistant/test_embedding.py
git commit -m "feat: add deterministic hash embedding"
```

---

### Task 3: InMemoryVectorStore（余弦检索）

**Files:**
- Create: `contexts/teaching_assistant/infrastructure/vector_store.py`
- Test: `tests/contexts/teaching_assistant/test_vector_store.py`

**Interfaces:**
- Consumes: Task 1 的 `VectorStorePort`/`Chunk`/`ScoredChunk`、Task 2 的 `HashEmbedding`。
- Produces: `InMemoryVectorStore`（`__init__(self, embedding: EmbeddingPort)`、`upsert(chunks: list[Chunk]) -> None`、`search(embedding: list[float], top_k: int) -> list[ScoredChunk]`，实现 `VectorStorePort`）。

- [ ] **Step 1: 写失败测试** `tests/contexts/teaching_assistant/test_vector_store.py`

```python
from contexts.teaching_assistant.domain.chunks import Chunk
from contexts.teaching_assistant.infrastructure.embedding import HashEmbedding
from contexts.teaching_assistant.infrastructure.vector_store import InMemoryVectorStore


def _chunk(chunk_id, text, heading="2.1"):
    return Chunk(chunk_id=chunk_id, chapter_id="c1", course_id="course1",
                 text=text, heading_path="第2章 > " + heading, source_ref=heading)


def test_search_returns_top_k_by_relevance():
    store = InMemoryVectorStore(HashEmbedding())
    store.upsert([
        _chunk("chunk_a", "循环结构 用于 重复 执行 代码"),
        _chunk("chunk_b", "变量 用于 存储 数据"),
        _chunk("chunk_c", "循环 结构 重复 执行"),
    ])
    results = store.search(HashEmbedding().embed("什么是循环结构"), top_k=2)
    assert len(results) == 2
    assert results[0].chunk.chunk_id == "chunk_a" or results[0].chunk.chunk_id == "chunk_c"
    assert results[0].score >= results[1].score


def test_upsert_dedupes_by_chunk_id():
    store = InMemoryVectorStore(HashEmbedding())
    store.upsert([_chunk("chunk_a", "循环结构 重复 执行")])
    store.upsert([_chunk("chunk_a", "循环结构 重复 执行")])
    results = store.search(HashEmbedding().embed("循环结构"), top_k=10)
    assert len(results) == 1


def test_search_empty_store_returns_empty():
    store = InMemoryVectorStore(HashEmbedding())
    assert store.search(HashEmbedding().embed("任意问题"), top_k=5) == []


def test_search_zero_vector_query_does_not_crash():
    store = InMemoryVectorStore(HashEmbedding())
    store.upsert([_chunk("chunk_a", "循环结构 重复 执行")])
    results = store.search([0.0] * 256, top_k=5)
    assert len(results) == 1
    assert results[0].score == 0.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_vector_store.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.teaching_assistant.infrastructure.vector_store'`）

- [ ] **Step 3: 实现 `InMemoryVectorStore`**

内部 `dict[chunk_id, (Chunk, list[float])]`。`upsert` 对每块 `embedding.embed(text)` 存向量，按 `chunk_id` 覆盖。`search` 计算 query 向量与各块余弦（`dot/(|a||b|)`，任一零范数返回 0.0），降序取前 `top_k`。

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_vector_store.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/teaching_assistant/infrastructure/vector_store.py tests/contexts/teaching_assistant/test_vector_store.py
git commit -m "feat: add in-memory vector store with cosine search"
```

---

### Task 4: StubHandoff + TeachingRepository

**Files:**
- Create: `contexts/teaching_assistant/infrastructure/handoff.py`
- Create: `contexts/teaching_assistant/infrastructure/repository.py`
- Test: `tests/contexts/teaching_assistant/test_handoff.py`
- Test: `tests/contexts/teaching_assistant/test_repository.py`

**Interfaces:**
- Consumes: Task 1 的 `HandoffPort`；`shared.infrastructure.db.models.sync_cache.Chapter`。
- Produces:
  - `StubHandoff`（`create_handoff(question: str, student_id: str | None) -> str`，实现 `HandoffPort`）
  - `TeachingRepository`（`__init__(self, session: Session)`、`list_chapters() -> list[Chapter]`）

- [ ] **Step 1: 写失败测试** `test_handoff.py` 与 `test_repository.py`

```python
# test_handoff.py
from contexts.teaching_assistant.infrastructure.handoff import StubHandoff


def test_create_handoff_returns_ticket_id():
    h = StubHandoff()
    ticket = h.create_handoff("什么是循环结构", "s_1")
    assert ticket.startswith("ticket_")
```

```python
# test_repository.py
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Chapter
from contexts.teaching_assistant.infrastructure.repository import TeachingRepository


def _repo(chapters=()):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    for c in chapters:
        s.add(Chapter(**c))
    s.commit()
    return TeachingRepository(s)


def test_list_chapters_returns_all():
    repo = _repo([dict(chapter_id="c1", title="t1", content_md="正文1"),
                  dict(chapter_id="c2", title="t2", content_md="正文2")])
    ids = {c.chapter_id for c in repo.list_chapters()}
    assert ids == {"c1", "c2"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_handoff.py tests/contexts/teaching_assistant/test_repository.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `StubHandoff` 与 `TeachingRepository`**

`StubHandoff.create_handoff` 返回 `"ticket_" + uuid.hex[:12]`。`TeachingRepository.list_chapters` 用 `select(Chapter)` 返回全部章节（不过滤 `content_md`，空内容由 `build_chunks` 处理）。

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_handoff.py tests/contexts/teaching_assistant/test_repository.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/teaching_assistant/infrastructure/handoff.py contexts/teaching_assistant/infrastructure/repository.py tests/contexts/teaching_assistant/test_handoff.py tests/contexts/teaching_assistant/test_repository.py
git commit -m "feat: add stub handoff and chapter repository"
```

---

### Task 5: TeachingAssistantService（编排）

**Files:**
- Create: `contexts/teaching_assistant/application/__init__.py`
- Create: `contexts/teaching_assistant/application/service.py`
- Test: `tests/contexts/teaching_assistant/test_service.py`

**Interfaces:**
- Consumes: Task 1 的 `Chunk`/`SCORE_THRESHOLD`/`HANDOFF_KEYWORDS`/三个端口；Task 2 的 `HashEmbedding`；Task 3 的 `InMemoryVectorStore`；Task 4 的 `StubHandoff`；`shared.infrastructure.llm.port.LLMPort`/`LLMResult`、`shared.infrastructure.llm.fake.FakeLLMAdapter`。
- Produces:
  - `TeachingAssistantService`（`__init__(self, llm: LLMPort, embedding: EmbeddingPort, vector_store: VectorStorePort, handoff: HandoffPort)`、`ask(self, question: str, student_id: str | None) -> dict`）
  - `ask` 返回 `{"reply": str, "sources": list[dict], "handoff": bool}`；`sources` 元素为 `{"chapterId", "headingPath", "sourceRef"}`。

- [ ] **Step 1: 写失败测试** `tests/contexts/teaching_assistant/test_service.py`

```python
from contexts.teaching_assistant.application.service import TeachingAssistantService, HANDOFF_REPLY
from contexts.teaching_assistant.domain.chunks import Chunk
from contexts.teaching_assistant.infrastructure.handoff import StubHandoff
from contexts.teaching_assistant.infrastructure.vector_store import InMemoryVectorStore
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubEmbedding:
    """按文本是否含关键词返回同向/正交向量，保证分数可控（不依赖真实 embedding 质量）。"""
    def embed(self, text: str) -> list[float]:
        if "循环" in text or "什么是" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


def _chunk(chunk_id, text, heading="2.1"):
    return Chunk(chunk_id=chunk_id, chapter_id="c1", course_id="course1",
                 text=text, heading_path="第2章 > " + heading, source_ref=heading)


def _service(llm_responses=None, chunks=None):
    embedding = _StubEmbedding()
    store = InMemoryVectorStore(embedding)
    if chunks:
        store.upsert(chunks)
    llm = FakeLLMAdapter(responses=llm_responses or ["讲解内容"])
    return TeachingAssistantService(llm, embedding, store, StubHandoff())


def test_ask_handoff_on_keyword():
    svc = _service()
    r = svc.ask("我要转人工", "s_1")
    assert r["handoff"] is True
    assert r["reply"] == HANDOFF_REPLY
    assert r["sources"] == []


def test_ask_handoff_on_empty_question():
    svc = _service()
    r = svc.ask("   ", None)
    assert r["handoff"] is True


def test_ask_handoff_on_empty_store():
    svc = _service()
    r = svc.ask("什么是循环结构", None)
    assert r["handoff"] is True


def test_ask_returns_llm_reply_and_sources():
    svc = _service(
        llm_responses=["循环结构用于重复执行一段代码。"],
        chunks=[_chunk("chunk_a", "循环结构 用于 重复 执行 一段 代码")],
    )
    r = svc.ask("什么是循环结构", None)
    assert r["handoff"] is False
    assert r["reply"] == "循环结构用于重复执行一段代码。"
    assert r["sources"][0]["chapterId"] == "c1"
    assert r["sources"][0]["headingPath"] == "第2章 > 2.1"
    assert r["sources"][0]["sourceRef"] == "2.1"


def test_ask_excludes_low_score_chunks_from_sources():
    # 命中块（含「循环」→ score 1.0）与无关块（→ score 0.0 < 阈值）并存
    svc = _service(
        llm_responses=["讲解"],
        chunks=[
            _chunk("chunk_hit", "循环 结构 重复 执行", heading="2.1"),
            _chunk("chunk_irrelevant", "完全无关 的 内容 主题 别的 领域 词汇", heading="2.9"),
        ],
    )
    r = svc.ask("什么是循环结构", None)
    assert r["handoff"] is False
    source_refs = [s["sourceRef"] for s in r["sources"]]
    assert "2.1" in source_refs           # 命中块进入 sources
    assert "2.9" not in source_refs       # 无关块（score 0.0）被排除

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_service.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.teaching_assistant.application'`）

- [ ] **Step 3: 实现 `TeachingAssistantService`**

`ask` 流程（钉死）：
1. `question` 为空白，或含 `HANDOFF_KEYWORDS` 任一 → `create_handoff`，返回 `{"reply": HANDOFF_REPLY, "sources": [], "handoff": True}`。
2. `emb = embedding.embed(question)`；`scored = vector_store.search(emb, TOP_K=5)`。
3. `max_score = max((s.score for s in scored), default=-1.0)`；`max_score < SCORE_THRESHOLD` → 转人工（同上）。
4. `hits = [s.chunk for s in scored if s.score >= SCORE_THRESHOLD]`；用 hits 拼 prompt（系统提示 + 学员问题 + 各块 `heading_path`/`source_ref`/`text`），`reply = llm.chat(messages).content`。
5. 返回 `{"reply": reply, "sources": [{"chapterId","headingPath","sourceRef"}...], "handoff": False}`。

常量 `HANDOFF_REPLY`（如 `"已为你转接授课老师，请稍候。"`）、`TOP_K = 5`、`ANSWER_SYSTEM_PROMPT` 均放 `service.py`。

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/contexts/teaching_assistant/test_service.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/teaching_assistant/application tests/contexts/teaching_assistant/test_service.py
git commit -m "feat: add teaching assistant ask orchestration"
```

---

### Task 6: 接口层 + API 端点

**Files:**
- Create: `contexts/teaching_assistant/interface/__init__.py`
- Create: `contexts/teaching_assistant/interface/schemas.py`
- Create: `contexts/teaching_assistant/interface/routes.py`
- Create: `contexts/teaching_assistant/interface/dependencies.py`
- Modify: `api/main.py`
- Test: `tests/test_teaching_api.py`

**Interfaces:**
- Consumes: Task 5 的 `TeachingAssistantService`；Task 1 的 `build_chunks`；Task 2/3/4 的 `HashEmbedding`/`InMemoryVectorStore`/`StubHandoff`；`shared.infrastructure.db.session.get_session`、`shared.infrastructure.llm.factory.get_llm`、`shared.infrastructure.config.get_settings`、`shared.infrastructure.web.response.ok`、`shared.infrastructure.observability.tracing.get_trace_id`。
- Produces: `AskRequest`（`question: str`、`studentId: str | None = None`）；`router`（`APIRouter(prefix="/api/v1/teaching")`，`POST /ask`）；`get_teaching_assistant_service(session) -> TeachingAssistantService`。

- [ ] **Step 1: 写失败测试** `tests/test_teaching_api.py`

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Chapter
from api.main import create_app
from contexts.teaching_assistant.application.service import TeachingAssistantService
from contexts.teaching_assistant.domain.chunks import Chunk
from contexts.teaching_assistant.infrastructure.embedding import HashEmbedding
from contexts.teaching_assistant.infrastructure.handoff import StubHandoff
from contexts.teaching_assistant.infrastructure.vector_store import InMemoryVectorStore
from contexts.teaching_assistant.interface.dependencies import get_teaching_assistant_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter


def _client(seed=None):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    if seed:
        seed(s)
        s.commit()

    def override_session():
        yield s

    def override_service():
        embedding = HashEmbedding()
        store = InMemoryVectorStore(embedding)
        store.upsert([Chunk(chunk_id="chunk_a", chapter_id="c1", course_id="course1",
                            text="循环结构 用于 重复 执行 代码",
                            heading_path="第2章 > 2.1", source_ref="2.1")])
        return TeachingAssistantService(FakeLLMAdapter(responses=["循环结构讲解"]),
                                        embedding, store, StubHandoff())

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_teaching_assistant_service] = override_service
    return TestClient(app)


def test_teaching_ask_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/teaching/ask", json={"question": "什么是循环结构"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["handoff"] is False
    assert body["data"]["reply"] == "循环结构讲解"
    assert body["data"]["sources"][0]["chapterId"] == "c1"


def test_teaching_ask_endpoint_validation_error():
    c = _client()
    r = c.post("/api/v1/teaching/ask", json={})
    assert r.status_code == 400
    assert r.json()["code"] == 40000
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/test_teaching_api.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.teaching_assistant.interface'`）

- [ ] **Step 3: 实现 `schemas.py` / `routes.py` / `dependencies.py`，并改 `api/main.py`**

`schemas.py`：`AskRequest`（`question: str`、`studentId: str | None = None`）。

`routes.py`：`router = APIRouter(prefix="/api/v1/teaching", tags=["teaching"])`；`@router.post("/ask")` 调 `service.ask(body.question, body.studentId)`，用 `ok(data=..., trace_id=get_trace_id())`。

`dependencies.py`：模块级单例 `_embedding = HashEmbedding()`、`_vector_store = InMemoryVectorStore(_embedding)`、`_handoff = StubHandoff()`；`get_teaching_assistant_service(session)` 内：`repo = TeachingRepository(session)`，对每个 `repo.list_chapters()` 调 `_vector_store.upsert(build_chunks(chapter.chapter_id, chapter.course_id, chapter.title, chapter.content_md))`，再返回 `TeachingAssistantService(...)`。

`api/main.py`：`from contexts.teaching_assistant.interface.routes import router as teaching_router` + `app.include_router(teaching_router)`。

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest tests/test_teaching_api.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 运行全量测试**

Run: `D:/projects/项目阶段/ai-assistant-platform/.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（104 + 新增 ≈ 128，0 失败）

- [ ] **Step 6: 提交**

```bash
git add contexts/teaching_assistant/interface api/main.py tests/test_teaching_api.py
git commit -m "feat: add teaching assistant ask endpoint"
```

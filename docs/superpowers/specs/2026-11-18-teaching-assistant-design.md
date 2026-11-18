# 助教 Agent（teaching_assistant）设计

- 日期：2026-11-18
- 状态：待确认
- 上游：《需求规格说明书》8.2.3 FR-008、《系统技术设计说明书》5.3 / 6.3 / 8.2

## 1. 意图与背景

落地课后答疑助教：学员就课程内容提问，系统基于课件 Markdown 检索相关分块，由 LLM 生成知识点讲解并溯源到课件位置；检索置信度不足或学员明确要求时转授课老师。面向已购课/VIP 学员，把「课后答疑依赖人工、响应慢、难溯源」的痛点转为可自动化、可溯源的答疑能力。

## 2. 目标 / 非目标 / 反目标

**目标**
- FR-008 答疑：问题向量化 → 检索课件分块 → LLM 生成讲解。
- 溯源定位：回答携带 `chapterId` + 标题层级 `headingPath` + 原文引用 `sourceRef`。
- 未解决转人工：低置信度 / 学员明确要求 → 走转人工端口（stub）。

**非目标（本阶段不做）**
- 不引真实 Milvus / 真实 embedding 模型（用户已定：端口 + 内存实现）。
- 不引 LangGraph（沿用阶段 2：纯 Service + 端口）。
- 不做 FR-009 智能督学（短信/微信触达，属后续阶段）。
- 不做 FR-006/007 学习路径规划（课程 Agent，低优先级）。
- 不做课件向量化的离线同步任务（分块/索引按需或幂等 upsert，真实离线管道留后续）。
- 不查真实教师-学生分配关系、不生成真实转人工工单（端口 + stub）。

**反目标（做了即算失败）**
- 破坏 DDD 依赖规则（teaching_assistant 只依赖 shared + 自身）。
- 低置信度时编造答案（必须转人工，不得用无关分块强行生成）。
- 返回无法溯源的回答（命中分块必须携带 chapterId/headingPath/sourceRef）。

## 3. 约束

- 沿用阶段 0/1/2：Python 3.11+、FastAPI、SQLAlchemy 2.x、Pydantic v2、structlog。
- LLM 走 `shared.infrastructure.llm.LLMPort`（纯文本 chat，`LLMResult.content`）；无 JSON mode / 无工具调用。
- 复用阶段 0 已建表：`Chapter`（含 `content_md` / `chapter_id` / `course_id`）——本阶段**不新增表**、**不新增依赖**。
- 测试零外部依赖（内存 SQLite、内存向量、确定性 embedding、FakeLLM）。

## 4. 关键决策（approaches）

| 决策点 | 候选 | 选定 | 理由 |
|--------|------|------|------|
| 向量检索/Embedding | ① 真实 Milvus + embedding 模型 ② 端口 + 内存实现 | **② 端口 + 内存实现** | 用户确认；与阶段 1/2 的「端口 + 内存/stub」一致，测试零外部依赖；真实 Milvus 经 `VectorStorePort` 后续可无痛替换 |
| 编排方式 | ① LangGraph ② 纯 Service + 端口 | **② 纯 Service** | 沿用阶段 2 已定路线 |
| 范围 | ① 仅 FR-008 ② FR-008 + FR-009 督学 | **① 仅 FR-008 + 溯源 + 转人工** | 用户确认；督学是定时任务 + 外部消息通道，差异大，拆后续 |

## 5. 架构

### 5.1 目录结构（沿用阶段 2 分层，接口收进领域 `interface/`）

```
contexts/teaching_assistant/
  domain/
    chunks.py       # Chunk/ScoredChunk 数据类 + chunk_markdown 纯函数 + 置信度阈值/转人工关键词
    ports.py        # EmbeddingPort / VectorStorePort / HandoffPort
  application/
    service.py      # TeachingAssistantService（编排）
  infrastructure/
    embedding.py    # HashEmbedding（确定性哈希向量）
    vector_store.py # InMemoryVectorStore（余弦检索）
    handoff.py      # StubHandoff
  interface/
    schemas.py      # AskRequest
    routes.py       # POST /api/v1/teaching/ask
    dependencies.py # get_teaching_assistant_service + 向量库单例
api/main.py         # + import & include teaching_router
tests/contexts/teaching_assistant/test_chunks.py
tests/contexts/teaching_assistant/test_service.py
tests/test_teaching_api.py
```

> 约定：领域对外接口（路由 + 请求/响应模型 + 装配）一律放在各领域的 `interface/`，不放在外部 `api/`。统一响应信封 `ok()` / `ApiResponse` 位于 `shared/infrastructure/web/response.py`（`api/schemas` 已废弃）。

### 5.2 确定性 / LLM 分工

| 环节 | 实现 |
|------|------|
| 分块 | 确定性（`chunk_markdown`：按 Markdown 标题层级分块） |
| Embedding | 确定性（`HashEmbedding`：字符 n-gram 哈希向量） |
| 检索 | 确定性（`InMemoryVectorStore`：余弦相似度 Top-K） |
| 置信度判断 / 转人工 | 确定性（阈值 + 关键词） |
| 讲解生成 | LLM（基于检索分块生成，纯文本） |
| 溯源定位 | 确定性（从检索结果携带 chapterId/headingPath/sourceRef） |

### 5.3 端口契约

```python
# domain/ports.py
@dataclass
class Chunk:
    chunk_id: str
    chapter_id: str
    course_id: str
    text: str
    heading_path: str   # 如 "第2章 > 2.3 循环结构"
    source_ref: str     # 段落锚点引用

@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float

class EmbeddingPort(Protocol):
    def embed(self, text: str) -> list[float]: ...

class VectorStorePort(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def search(self, embedding: list[float], top_k: int) -> list[ScoredChunk]: ...

class HandoffPort(Protocol):
    def create_handoff(self, question: str, student_id: str | None) -> str: ...
```

### 5.4 分块与 Embedding 规则（我的实现裁定）

- **分块**：按 Markdown 标题层级切分，保留标题上下文（`heading_path`），单块约 300–800 字符，重叠 50–100 字符；`chunk_id` 确定性生成（见 §8 第 4 条，幂等 upsert）。
- **Embedding**：字符 n-gram（如 2/3-gram）哈希 trick，固定维度（如 256），**非负**计数向量 + L2 归一化；余弦相似度即分块与问题的相关性。
- **置信度阈值**：`SCORE_THRESHOLD = 0.3`（模块级常量）。Top-K 检索 K=5；最高分 < 阈值 → 转人工。

### 5.5 数据流（ask）

```
用户提问 question
 → 关键词判断（含「转人工/找老师/人工客服」）→ 命中直接转人工
 → embedding.embed(question)
 → vector_store.search(embedding, top_k=5)
 → max(score) < SCORE_THRESHOLD → 转人工
 → 否则 LLM 基于检索分块（text + heading_path + source_ref）生成讲解
 → 返回 {reply, sources, handoff}
```

- 转人工：`handoff.create_handoff(question, student_id)`（stub 返回 ticket id），`reply = HANDOFF_REPLY`、`sources = []`、`handoff = True`。
- 正常回答：`reply` 为 LLM 讲解，`sources` 为命中分块的 `[{chapterId, headingPath, sourceRef}]`，`handoff = False`。

## 6. API 契约

`POST /api/v1/teaching/ask`（统一响应 `{code, message, data, traceId}`）

**请求**：
```json
{"question": "什么是循环结构", "studentId": "s_xxx（可空）"}
```

**响应 data**：
```json
{
  "reply": "循环结构用于重复执行一段代码……",
  "sources": [{"chapterId": "ch1", "headingPath": "第2章 > 2.3 循环结构", "sourceRef": "2.3 节"}],
  "handoff": false
}
```

- `handoff=True` 时：`reply = HANDOFF_REPLY`、`sources = []`。

## 7. 留给实施者的自由度

- Embedding 的具体 n-gram 取值与向量维度、分块重叠量。
- 检索 Top-K 与置信度阈值的精确取值（本设计给默认 5 / 0.3，实施可微调但须测试锁定）。
- 讲解生成 prompt 的具体措辞。
- 分块索引（读 `Chapter.content_md` → 分块 → embed → upsert）在 API 装配层的触发方式（启动即索引 / 首次请求懒加载 / 依赖注入时预置），以测试可种子化为准。
- 文件内模块切分粒度、`StubHandoff` 返回的 ticket id 格式。

## 8. 补充决策（构建者核查后确定）

构建者核查后补充的裁定，实施者照此执行：

1. **Chapter 读取**：新增 `contexts/teaching_assistant/infrastructure/repository.py` 的 `TeachingRepository`（镜像 `SalesRepository`），暴露 `list_chapters() -> list[Chapter]`（可按 `course_id` 过滤）。Service 不接触 Session；读库在 API 装配层完成。
2. **向量库单例**：`InMemoryVectorStore` 以模块级单例注入（镜像 `_sales_memory`），跨请求存活。索引在依赖注入时预置（读全部 `Chapter.content_md` → 分块 → embed → upsert），测试可种子化。
3. **heading_path / source_ref 派生**：`Chapter` 表仅有 `title` + `content_md`（无层级/排序字段，见 `sync_cache.py`）。`heading_path = title + " > " + content_md 内标题路径`（`content_md` 内标题为 `## 2.3 循环结构` 形式）；`source_ref` = 最内层标题标签（无内层标题时回退为 `title`）；`chapter_id` 直接取 `Chapter.chapter_id`。
4. **chunk_id 幂等**：`chunk_id` 确定性生成——`"chunk_" + sha1(f"{chapter_id}|{heading_path}|{块序号}")[:12]`；`upsert` 以 `chunk_id` 去重（同 id 覆盖），保证重复索引幂等。
5. **命中分块口径**：`sources` 与 LLM prompt 仅包含 `score >= SCORE_THRESHOLD` 的分块（非全部 Top-K）；`max(score) < SCORE_THRESHOLD` → 转人工。至少保证 top-1 命中。
6. **Embedding 语义**：`HashEmbedding` 用**非负**字符 n-gram 计数向量（L2 归一化后余弦 ∈ [0,1]，阈值 0.3 才有「相似度」意义）；空/空白文本分块直接跳过，`embed("")` 返回零向量。
7. **空库 / 结果不足**：`search` 返回空列表时按「未命中」处理（`max` 视为 `-inf`，低于阈值）→ 转人工，不抛异常；空问题同样走转人工。

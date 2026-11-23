# sales_assistant FAQ 知识库（RAG）迁移设计

- 日期：2026-11-20
- 状态：待确认
- 上游：`docs/superpowers/specs/2026-11-18-sales-assistant-design.md`、旧项目 `D:\projects\mbz_agent_project`（智能营销助手 RAG 问答）

## 1. 意图与背景

把旧项目（`mbz_agent_project`）里已实现、验证过的**营销 FAQ 知识库 + 语义检索**能力，迁移进当前项目的 `sales_assistant`，替换其现有的「4 条硬编码关键词 FAQ + 裸 LLM 兜底」薄实现。迁移只动 FAQ 路径，意图识别 / 课程推荐 / 线索留资不动。

> 本设计**取代** `2026-11-18-sales-assistant-design.md` 中「非目标：不引向量库/RAG（Milvus 属阶段 3）」与「FAQ 知识来源 = 内置确定性 FAQ」两条决策——即本迁移就是"阶段 3"的 Milvus/RAG 落地。

## 2. 目标 / 非目标 / 反目标

**目标**
- 用旧项目知识库（`data/智能营销助手知识库（可上线部分）.md`，几十条真实 FAQ）替换硬编码 FAQ。
- 引入真语义检索：BGE-M3 稠密向量 + Milvus Lite，默认 `dense`、保留 `hybrid`（dense + BM25 加权）开关。
- FAQ 回答可溯源（响应返回 `sources`）。

**非目标（本次不做）**
- 不动意图识别、方向/岗位归一化、课程推荐、线索留资（保留现状）。
- 不做 `/ask/stream` 流式（当前 `LLMPort` 无 stream）。
- 不迁移旧项目的死代码（`llm.py`、`cache.py`、`recursion_split_vectorstore.py`，README 自注废弃）。

**反目标（做了即算失败）**
- 破坏 DDD 依赖规则：`sales_assistant` 仍只依赖 `shared` + 自身，不 import 其他 context。
- 生成回答绕过共享 `LLMPort`（不允许在 sales_assistant 内自行 new `ChatOpenAI`）。
- FAQ 命中不溯源（丢失 `sources`）。

## 3. 约束

- 沿用：Python 3.11+、FastAPI、SQLAlchemy 2.x、Pydantic v2、structlog。
- LLM 生成走 `shared.infrastructure.llm.LLMPort.chat() -> LLMResult`。
- 接受重依赖（用户已确认）：torch、sentence-transformers、transformers、pymilvus、langchain-milvus、langchain-huggingface、langchain-text-splitters。
- 检索默认 `dense`，`hybrid` 由环境变量切换（照搬旧项目 `RETRIEVAL_MODE`）。
- 知识库为**静态种子数据**（Markdown 文件 + 一次性建库脚本），不新增 DB 表。

## 4. 关键决策（approaches）

| 决策点 | 候选 | 选定 | 理由 |
|--------|------|------|------|
| 检索后端 | ① HashEmbedding+InMemoryVectorStore ② FTS5/BM25 纯关键词 ③ BGE-M3 + Milvus | **③ BGE-M3 + Milvus（dense 默认 / hybrid 开关）** | 用户拍板"参考旧项目"；真语义检索、旧项目已跑通；接受重依赖 |
| 端口形态 | ① EmbeddingPort+VectorStorePort 拆两半（仿 teaching_assistant）② 单一 KnowledgeBasePort.search(text) | **② 单一 `KnowledgeBasePort.search(question, top_k) -> list[FaqHit]`** | 旧项目 Milvus 自带 embedding_function，应用层无需感知 embedding；更贴旧项目形态 |
| FAQ 确定性表 | ① 保留 `match_faq` 作前置 ② 整体替换为知识库检索 | **② 移除 `FAQ_ENROLLMENT`/`FAQ_STUDY`/`match_faq`** | 知识库即 FAQ 内容；BM25 稀疏路已承担"关键词确定性"角色 |
| 无命中兜底 | ① score_threshold 过滤 → 空即转人工 ② 恒取 top-k + 生成 prompt「勿编造」兜底 | **② 恒取 top-k（默认无阈值），prompt 兜底** | 照搬旧项目 `/ask` 默认 `score_threshold=None`；检索恒有结果，由 LLM 判可否答 |

## 5. 架构

### 5.1 目录结构（变更部分）

```
contexts/sales_assistant/
  domain/
    directions.py        # 保留：方向/岗位归一化；删除 FAQ 表与 match_faq
    faq.py               # 新增：FaqHit 类型 + FAQ 常量（TOP_K / 无命中回复）
    ports.py             # 扩展：+ KnowledgeBasePort
  application/
    service.py           # 扩展：_handle_faq 改为 检索→LLM 生成；chat 响应 + sources
  infrastructure/
    embeddings.py        # 新增：BGE-M3 适配器（port 旧项目 create_embeddings）
    knowledge_base.py    # 新增：MilvusKnowledgeBase（search）+ build() 建库
    repository.py        # 保留
    vip_report.py        # 保留
  data/
    智能营销助手知识库.md  # 新增：旧项目知识库内容
  interface/             # 保留（chat 端点不变）
shared/infrastructure/config.py   # 扩展：+ embedding_model / milvus_uri / retrieval_mode / sales_faq_top_k
pyproject.toml                    # 扩展：+ 重依赖
```

### 5.2 端口契约（新增）

```python
# contexts/sales_assistant/domain/faq.py
@dataclass
class FaqHit:
    question: str
    content: str
    score: float

# contexts/sales_assistant/domain/ports.py
class KnowledgeBasePort(Protocol):
    def search(self, question: str, top_k: int = 4) -> list[FaqHit]: ...
```

### 5.3 FAQ 数据流（chat 内 FAQ 分支）

```
enrollment_faq / study_faq 意图
 → KnowledgeBasePort.search(question, top_k=TOP_K)
 → 空命中 → FAQ_NO_MATCH_REPLY（引导留资/转顾问老师）
 → 非空 → 拼「知识库上下文 + 用户问题」prompt → LLMPort.chat → 生成回答
 → 响应附 sources=[{question, content, score}]
```

## 6. API 契约变更

`POST /api/v1/sales/chat` 响应 `data` 增加 `sources` 字段：

```json
{
  "conversationId": "c_xxx",
  "reply": "...",
  "direction": "AI",
  "position": "大模型算法岗",
  "courses": [],
  "leadSaved": false,
  "sources": [{"question": "…", "content": "…", "score": 0.77}]
}
```

- `sources`：仅 FAQ 分支非空，其余分支恒为 `[]`。

## 7. 依赖变更（pyproject.toml）

新增：`langchain-milvus`、`langchain-huggingface`、`langchain-text-splitters`、`pymilvus`、`sentence-transformers`、`transformers`；`torch` 按机器单独装（CPU/CUDA 自选，同旧项目 requirements.txt 注释）。

## 8. 配置变更（shared/infrastructure/config.py）

```python
embedding_model: str = "BAAI/bge-m3"
milvus_uri: str = ""          # 空则解析为项目根 data/ 下 milvus_sales_faq.db
retrieval_mode: Literal["dense", "hybrid"] = "dense"
sales_faq_top_k: int = 4
```

## 9. 补充决策（构建者核查后定，交付可复核）

1. **移除确定性 FAQ 表**：删除 `directions.py` 的 `FAQ_ENROLLMENT`/`FAQ_STUDY`/`match_faq`，同步删除 `test_directions.py` 的 `match_faq` 测试；`test_sales_service.py` 中 `test_chat_faq_hit_deterministic` / `test_chat_faq_miss_llm_fallback` 改为基于 `KnowledgeBasePort` 假实现。
2. **生成 prompt**：迁移旧项目 `rag_service.py` 的 `SYSTEM_PROMPT`（"严格基于知识库、勿编造、勿暴露信息来源、口语化"）。
3. **hybrid 权重** `[0.7, 0.3]` 作为适配器模块常量（非 env，同旧项目）；`retrieval_mode` 走 Settings/env。
4. **建库方式**：一次性脚本（`python -m contexts.sales_assistant.infrastructure.build_knowledge_base`），读 `data/*.md` → 清洗 → 按 `###` 切 FAQ → 写入 Milvus（dense + sparse BM25 双字段）；运行时适配器只 load 不建。
5. **Milvus 加载时机**：适配器实例化时 load（进程常驻），不做教学助手的懒 `_ensure_indexed`——因为 BGE-M3 加载重，首次请求懒加载会拖垮首请求。

## 10. 留给实施者的自由度

- FAQ 切块的精确实现（是否用 LangChain `MarkdownHeaderTextSplitter` 还是纯正则按 `###` 切；超长 FAQ 二次切分是否沿用 tokenizer 版）。
- `TOP_K`、`FAQ_NO_MATCH_REPLY` 文案、生成 prompt 的最终措辞。
- Milvus Lite 文件的确切路径与 `milvus_uri` 默认解析逻辑。
- `build_knowledge_base` 是否复用旧项目 `head_split_vectorstore.py` 的 `clean_markdown`/二次切分逻辑（建议复用其纯函数部分）。

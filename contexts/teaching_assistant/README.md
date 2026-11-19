# teaching_assistant（智能助教 / 答疑 RAG）

面向**课后答疑**场景的助教 Agent：把课件按标题切块向量化，检索与学员问题最相关的分块，交给 LLM 生成带溯源的解答；检索不到或明确要求时转人工。

## 职责

- 课件切块：按 Markdown 标题层级切分正文，保留标题路径与溯源引用（`heading_path` / `source_ref`）
- 向量检索：问题向量化后检索 Top-K 分块，按相似度阈值过滤
- 带溯源答疑：用命中的课件分块生成回答，附 `sources` 溯源信息
- 转人工：空问题、命中"转人工/找老师"关键词、或检索分数低于阈值时，创建转人工工单

## 分层结构

```
contexts/teaching_assistant/
├── domain/
│   ├── chunks.py       # Chunk/ScoredChunk + 切块逻辑 + 阈值/关键词
│   └── ports.py        # EmbeddingPort / VectorStorePort / HandoffPort
├── application/
│   └── service.py      # TeachingAssistantService（ask 编排）
├── infrastructure/
│   ├── embedding.py    # EmbeddingPort 适配器
│   ├── vector_store.py # VectorStorePort 适配器
│   ├── handoff.py      # HandoffPort 适配器
│   └── repository.py   # 课件/分块读取
└── interface/
    ├── routes.py       # REST 路由
    ├── schemas.py      # 请求模型
    └── dependencies.py # 依赖装配
```

## 端口

- **定义（对外提供）**：`EmbeddingPort.embed(text)`、`VectorStorePort.upsert/search`、`HandoffPort.create_handoff`
- **消费（依赖）**：`LLMPort`

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/teaching/ask` | 答疑入口，返回回答 + 溯源 sources + 是否转人工 |

## 依赖

- 仅依赖 `shared`
- 与其他 context 无依赖（`contexts-leaf-independent` 契约）

# teaching_assistant（智能助教 / 答疑 RAG）

面向**课后答疑**场景的助教 Agent：把课件 Markdown 按标题切块向量化（BGE-M3 + Milvus），检索与学员问题最相关的分块，交给 LLM 生成带溯源的解答；检索不到时返回固定「无法回答」文案。

## 职责

- 课件切块：按 Markdown 标题层级切分正文，保留标题路径（三层：标题 → 长度 → 重叠）
- 向量化：BGE-M3 嵌入 + Milvus 建库（离线脚本），集合 `teaching_assistant_chunks`
- 语义检索：问题 → Milvus 检索 Top-K 分块，按相似度阈值过滤
- 带溯源答疑：用命中的课件分块生成回答，附 `sources` 溯源信息
- 会话落库：每次问答写入 `conversation_message`（user + assistant 两条）

## 分层结构

```
contexts/teaching_assistant/
├── domain/
│   ├── chunks.py       # RetrievedChunk + 三层切块逻辑 + SCORE_THRESHOLD
│   └── ports.py        # RetrievalPort / ConversationRecordPort
├── application/
│   └── service.py      # TeachingAssistantService（ask / ask_stream 编排）
├── infrastructure/
│   ├── knowledge_base.py      # MilvusKnowledgeBase（BGE-M3 + Milvus 检索适配器）
│   ├── build_chunks.py        # 切片 CLI：data/docs/*.md → chunks.jsonl
│   ├── build_knowledge_base.py # 建库 CLI：chunks.jsonl → Milvus
│   └── conversation_repository.py # 会话记录适配器
└── interface/
    ├── routes.py       # REST 路由
    ├── schemas.py      # 请求模型
    └── dependencies.py # 依赖装配（懒加载 Milvus 单例）
```

## 端口

- **定义（对外提供）**：`RetrievalPort.search(question, top_k)`、`ConversationRecordPort`
- **消费（依赖）**：`LLMPort`

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/teaching/ask` | 答疑入口，返回回答 + 溯源 sources + conversationId |
| POST | `/api/v1/teaching/ask/stream` | SSE 流式答疑（meta/delta/done） |
| GET | `/api/v1/teaching/conversations` | 会话列表 |
| GET | `/api/v1/teaching/conversations/{conversationId}` | 会话消息 |

## 依赖

- 仅依赖 `shared`（`shared.infrastructure.embeddings.create_embeddings` 提供 BGE-M3）
- 与其他 context 无依赖（`contexts-leaf-independent` 契约）

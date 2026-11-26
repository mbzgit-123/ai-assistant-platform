# 助教 Agent：删除转人工 + 新增会话记录落库 设计

- 日期：2026-11-25
- 状态：已确认（2026-11-25，用户拍板表结构 8 字段）
- 上游：用户口头需求（需求文档当前未同步）
- 前置文档：`docs/superpowers/specs/2026-11-18-teaching-assistant-design.md`

## 1. 意图与背景

`teaching_assistant`（助教 Agent）已按 2026-11-18 设计完成并全量测试通过（215 passed）。现用户提出两处变更：

1. **删除「转人工」**：需求里「未解决问题转授课老师（联动教师-学生分配关系）」这条取消。`teacher` / `student_teacher_relation` 表此前已作为死表删除，转人工已无数据支撑，代码里的 `StubHandoff` 成为无意义 stub，一并移除。
2. **新增「会话记录管理」**：每次答疑（一问一答）落库，形成可查询的会话历史，替代原先「转人工」在答疑链路中的位置，作为答疑闭环的持久化产物。

## 2. 目标 / 非目标 / 反目标

**目标**
- 移除 teaching_assistant 中所有「转人工」代码（端口、stub、关键词、低置信度转人工分支、`handoff` 返回字段）。
- 答疑不再有「转人工」语义：检索不到时不转人工，改为如实告知「无法回答」。
- 每次答疑落库两条记录（用户问题 + 系统回答），支持按会话归组、按 `student_id` 查询。
- 同步需求文档：FR-008 去掉转人工，新增 FR-009 会话记录管理，清理其余「转授课老师/转人工」残留（仅答疑场景）。

**非目标（本阶段不做）**
- 不接「教师-学生分配关系」（关系表已删，数据源不在本平台边界内）。
- 不做会话记录的更新/删除/分页接口（只落库，查询接口留给后续，落库是唯一交付）。
- 不做真实消息通道触达老师（无转人工）。
- 不动其它上下文的「转人工」（如 exam_grading 的「批改异常转人工」保留）。

**反目标（做了即算失败）**
- 破坏 DDD 依赖规则（teaching_assistant 只依赖 shared + 自身）。
- 低置信度时编造答案（必须如实告知无法回答，不得用无关分块强行生成）。
- 落库失败阻塞答疑主流程（会话记录是附属，答疑本身是主功能）。

## 3. 约束

- 沿用：Python 3.11+ / FastAPI / SQLAlchemy 2.x / Pydantic v2 / structlog / pytest。
- LLM 走 `LLMPort.chat()`（纯文本）；无 JSON mode / 工具调用。
- 新增表 `conversation_message`，需走 alembic 迁移（MySQL，`alembic upgrade head`）。
- 测试零外部依赖：内存 SQLite（StaticPool）+ `FakeLLMAdapter` + 确定性 `HashEmbedding`。

## 4. 关键决策（approaches）

| 决策点 | 候选 | 选定 | 理由 |
|--------|------|------|------|
| 低置信度兜底 | ① 转人工（现状）② LLM 兜底如实说明 ③ 固定「无法回答」文案 | **③ 固定文案，不调 LLM** | 保留原「低置信度不编造」反目标；确定性强、零额外 LLM 成本、绝不编造 |
| 空题处理 | ① 进 service 转人工 ② schema 校验直接 400 | **② `min_length=1` → 400** | 空题是非法输入，接口层拦截更干净；走现有异常处理返回 `40000` |
| 会话落库范围 | ① 只落问题 ② 问+答都落 | **② 问+答（用户拍板）** | 才构成完整「会话记录」；assistant 记录携带溯源 |
| 会话归组 | ① 无 conversation_id ② 引入 conversation_id | **② 引入（用户拍板 A 方案）** | 多轮问答归组，是「记录管理」的基础；缺省自动生成并返回 |
| 落库失败语义 | ① 失败即抛 ② 记录日志不阻塞 | **② 记录日志不阻塞** | 会话记录是附属，不因记录失败破坏答疑主流程 |
| 落库端口 | ① 直接依赖 repository ② 走 `ConversationRecordPort` | **② 端口 + 适配器** | 遵循 DDD 依赖倒置，application 不碰 Session |

## 5. 方案一：删除转人工

### 5.1 代码改动清单

| 文件 | 操作 |
|------|------|
| `domain/chunks.py` | 删 `HANDOFF_KEYWORDS` 常量 |
| `domain/ports.py` | 删 `HandoffPort`；新增 `ConversationRecordPort`（见 §6.2） |
| `application/service.py` | 删 `HANDOFF_REPLY`、`_handoff_reply()`、关键词分支、低置信度转人工分支、`__init__` 的 `handoff` 参数、返回的 `handoff` 字段；新增低置信度固定文案分支、`conversation_record` 参数、落库调用、返回 `conversationId` |
| `infrastructure/handoff.py` | 整个文件删除 |
| `interface/dependencies.py` | 删 `_handoff` 单例与注入；注入 `ConversationRepository` |
| `interface/schemas.py` | `question` 加 `min_length=1`；新增 `conversationId: str | None = None` |
| `interface/routes.py` | `service.ask(body.question, body.studentId)` 改传 `body.conversationId` |
| 测试 | 删 `test_handoff.py`；改 `test_teaching_service.py` / `test_teaching_api.py`；`test_dependencies.py` 同步 |

### 5.2 删后兜底行为（钉死）

| 原触发 | 新行为 |
|--------|--------|
| 空/空白问题 | 接口层 400（`min_length=1`），不进 service |
| 含关键词（转人工/找老师/人工客服） | 整支删除，不再识别 |
| `max_score < 0.3`（检索不到） | 返回固定文案 `UNABLE_TO_ANSWER_REPLY`，`sources=[]`，**不调 LLM**，仍落库 |

`UNABLE_TO_ANSWER_REPLY`（模块级常量，放 `service.py`）：
`"暂未找到相关课件内容，无法回答，请换个问法或补充更多信息。"`

## 6. 方案二：会话记录落库

### 6.1 数据模型（`shared/infrastructure/db/models/business.py`）

```python
class ConversationMessage(Base):
    __tablename__ = "conversation_message"
    __table_args__ = (Index("ix_conversation_message_conv", "conversation_id"),)

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)   # "msg_" + uuid.hex[:12]
    conversation_id: Mapped[str] = mapped_column(String(64))                 # "conv_" + uuid.hex[:12]
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # teaching=studentId；sales 游客可空
    role: Mapped[str] = mapped_column(String(16))                            # "user" | "assistant"
    message: Mapped[str] = mapped_column(Text)                               # 问题原文 或 回答文本
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)        # assistant 的溯源列表
    source: Mapped[str] = mapped_column(String(16))                          # "sales" | "teaching"
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
```

- `role="user"`：`message`=问题原文，`sources=None`。
- `role="assistant"`：`message`=回答文本（含「无法回答」文案），`sources`=`[{chapterId, headingPath, sourceRef}]`（低置信度时 `[]`）。
- `source` 固定 `"teaching"`（本阶段只实现助教侧；sales 后续接入时写 `"sales"`）。
- 在 `models/__init__.py` 注册 `ConversationMessage`。

### 6.2 端口契约（`domain/ports.py`）

```python
class ConversationRecordPort(Protocol):
    def record_exchange(
        self,
        conversation_id: str,
        user_id: str | None,
        question: str,
        reply: str,
        sources: list[dict],
    ) -> None: ...
```

实现（`infrastructure/conversation_repository.py`，新建 `ConversationRepository`）：
- `__init__(self, session: Session)`，镜像 `TeachingRepository`。
- `record_exchange` 写两条 `ConversationMessage`（user + assistant），`commit` 由调用方决定或内部提交（见 §6.4）。

### 6.3 应用层编排（`service.py`）

`ask(self, question, student_id, conversation_id=None)` 流程：

1. `conversation_id = conversation_id or "conv_" + uuid.hex[:12]`（空则生成）。
2. 空题判断可移除（已由接口层 400 拦截），但保留 `question.strip()` 防御亦可。
3. `emb = embedding.embed(question)`；`scored = vector_store.search(emb, TOP_K=5)`。
4. `max_score = max(..., default=-1.0)`；`max_score < SCORE_THRESHOLD` →
   `reply = UNABLE_TO_ANSWER_REPLY`、`sources = []`（**不调 LLM**）。
5. 否则 `hits = [chunk for score >= 阈值]`，`reply = llm.chat(...).content`，`sources = [...]`。
6. **落库**：`conversation_record.record_exchange(conversation_id, user_id=student_id, question=question, reply=reply, sources=sources)`（失败 catch + log，不抛）。注：service 入参保留 `student_id`（API 语义），落库端口参数为 `user_id`（通用语义，teaching 场景 user_id=student_id）。
7. 返回 `{"reply": reply, "sources": sources, "conversationId": conversation_id}`。

### 6.4 依赖装配（`interface/dependencies.py`）

- 删 `_handoff`。
- `get_teaching_assistant_service(session)` 内：`ConversationRepository(session)` 传给 service（每个请求新建，不搞模块级单例，因依赖 session）。
- 注意：`ConversationRepository` 需 `session.commit()`；因 service 每次请求拿到同一 session（`get_session` 依赖），落库后提交即可。若未来 session 生命周期变化，实施者可把 commit 下沉到 repository（我的裁定：**repository 内 `record_exchange` 末尾 `session.commit()`**，service 不感知事务）。

### 6.5 API 契约（`interface/schemas.py` / `routes.py`）

**请求** `POST /api/v1/teaching/ask`：
```json
{"question": "什么是循环结构", "studentId": "s_xxx（可空）", "conversationId": "conv_xxx（可空）"}
```

**响应 data**：
```json
{
  "reply": "循环结构用于重复执行一段代码……",
  "sources": [{"chapterId": "ch1", "headingPath": "第2章 > 2.3 循环结构", "sourceRef": "2.3 节"}],
  "conversationId": "conv_xxx"
}
```

- 低置信度：`reply = UNABLE_TO_ANSWER_REPLY`、`sources = []`、仍返回 `conversationId`。
- 空题：400（`question` 缺省/空串），`code=40000`。

## 7. 需求文档改动清单

文件：`docs/码帮智 · 教育智能体平台需求规格说明书.md`

| 位置 | 现内容 | 改为 |
|------|--------|------|
| 7.3.3（307 行）第 3 条 | 未解决问题按教师-学生分配关系转授课老师 | 记录答疑会话（问题与回答落库） |
| 7.3.4（311 行）输出 | …课件定位；未解决时转人工 | …课件定位（删「未解决时转人工」） |
| 8.2.1 FR-008（384 行）功能描述 | …；未解决的问题转授课老师 | 删「；未解决的问题转授课老师」 |
| 8.2.1 FR-008（388 行）业务规则 | …检索回答；未解决问题转授课老师（联动教师-学生分配关系） | …检索回答（删后半句） |
| 8.2 新增 8.2.2（FR-008 后） | 无 | 新增 FR-009 会话记录管理（见下） |
| 9.1.2 答疑规则（529 行） | 未解决问题转授课老师（联动教师-学生分配关系） | 每次答疑记录会话（问题与回答落库） |
| 9.3 数据不足规则（559 行） | 必要时建议人工处理（转授课老师、转人工） | 如实告知信息不足（删「转人工」措辞） |
| 14.1 核心数据对象（736 行后） | 无 | 加 ConversationMessage 行 |
| 14.2 加 14.2.7 | 无 | ConversationMessage 字段表 |
| 17.1 功能验收 | 无 | 加 ACC-006 会话记录（能落库问答并可按会话查询） |

**FR-009 会话记录管理**（新增原文）：
- **功能描述**：答疑过程中记录每次会话的用户问题与系统回答，形成可按会话、按学员查询的历史记录。
- **输入**：学员问题、系统回答、溯源、会话 id、学员 id。
- **输出**：会话记录落库结果。
- **业务规则**：每次答疑落两条记录（`role` 区分 user/assistant）；assistant 记录携带溯源 `sources`；同一会话多轮问答归组到同一 `conversationId`；`conversationId` 缺省时自动生成并返回。

**注意**：11.4「批改异常 → 转人工」（640 行）与 ACC-013（924 行）属 exam_grading，**不改**。

## 8. 留给实施者的自由度

- `ConversationRepository` 的 `record_exchange` 是否内部 `commit`（我裁定：内部 commit）。
- `UNABLE_TO_ANSWER_REPLY` 文案措辞（给默认，可微调但测试锁定）。
- `conversation_id` / `message_id` 的 id 前缀与生成方式（给 `conv_`/`msg_` + uuid.hex[:12]）。
- 落库失败的日志级别与是否重试（默认 log 一次、不重试）。
- `models/__init__.py` 的导入顺序与 `__all__` 追加位置。
- 迁移文件命名（`alembic revision --autogenerate` 自动生成）。

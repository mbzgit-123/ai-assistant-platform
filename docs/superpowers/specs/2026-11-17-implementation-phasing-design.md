# 码帮智 · 教育智能体平台 — 分阶段实施设计

- 日期：2026-11-17
- 状态：待确认
- 上游文档：《需求规格说明书》V1.0、《系统技术设计说明书》V1.0

## 1. 意图与背景

依据两份已批准的文档，把「码帮智·教育智能体平台」从零实现为可运行的后端 AI 智能体中台。用户要求**分阶段实现，每阶段完成并由用户确认后再进入下一阶段**，以降低返工风险、逐步验证架构。

## 2. 目标 / 非目标 / 反目标

**目标**
- 按 v1.0（P0）范围交付：上下文骨架 + 共享基础设施 + 智能客服/路径规划/答疑/督学 + 自主练习闭环（出题/练习/批改）。
- 每阶段产出可运行、可测试的增量，而非一次性堆叠未验证代码。

**非目标（本阶段不做）**
- 前端界面（文档已明确本系统是后端中台）。
- v1.1/v1.2/v2.0 需求（换一批、题库模式、微服务拆分、第二梯队 Agent）。
- 视频 ASR 转写（ADR-05 已排除）。

**反目标（做了即算失败）**
- 破坏 DDD 依赖规则（context 间直接依赖、shared 依赖 context）。
- LLM 输出无确定性兜底，导致出题/判分不可靠。
- 为了"本地轻量"写死 SQLite，导致后续无法切换 MySQL。

## 3. 约束

- 技术栈遵循技术设计说明书：Python 3.11+（本机 3.13.5）、FastAPI、LangGraph、LangChain、SQLAlchemy 2.x、Pydantic v2。
- 本机现状：Python 3.13.5（anaconda）+ pip 25.1，无 `uv`，git 2.33，Docker 27.5.1 可用。
- LLM 供应商已定：DeepSeek（用户已持有 key）。
- 部署形态：模块化单体起步。

## 4. 关键决策（approaches 与选定）

| 决策点 | 候选 | 选定 | 理由 |
|--------|------|------|------|
| 运行环境 | ① Docker 全栈 ② 本地轻量优先 ③ 已有中间件 | **② 本地轻量优先** | 用户确认；最快跑通闭环，中间件通过端口预留，后续切 Docker |
| LLM 接入 | ① 纯 Mock ② DeepSeek 真实 ③ 通义 | **② DeepSeek + Mock 兜底** | 用户持有 key；客户端做成可注入，测试/离线用 Mock |
| 起点顺序 | ① 骨架优先 ② 垂直切片优先 | **① 骨架优先** | 用户确认；先立架构与依赖规则，再逐上下文填业务 |

## 5. 阶段划分

| 阶段 | 内容 | 交付物（验收点） |
|------|------|------------------|
| **阶段 0** | 工程骨架 + 共享基础设施 | DDD 目录、配置、统一异常/响应、SQLAlchemy 全量表 + Alembic、LLM 客户端（DeepSeek/Mock）、FastAPI 外壳 + `/health` `/ready`、依赖规则检查、pytest 基架 |
| **阶段 1** | 自主练习闭环（出题 + 练习 + 批改） | 确定性逻辑（截取/题量/题型/准入/判分）单测；4 个 practice API；题目复用；选择判分 + 主观批改 |
| **阶段 2** | 营销 Agent（智能客服） | 方向/岗位识别、课程推荐、FAQ 咨询、线索留资（FR-001~005） |
| **阶段 3** | 助教 Agent（答疑 RAG） | 课件向量化 + 检索 + 溯源 + 转人工（FR-008） |
| **阶段 4** | 课程 Agent + 督学 | 路径规划（FR-006/007）+ 督学定时（FR-009） |
| **阶段 5（可选）** | 学情分析接入 | v1.1 范围，单独评估 |

每阶段完成 → 用户确认 → 再进入下一阶段。阶段 1 起每个阶段用 `writing-plans` 产出独立实施计划并经确认。

## 6. 本地轻量优先的适配层设计（Ports & Adapters）

文档目标栈是 MySQL + Redis + Celery + Milvus。本地轻量阶段以**端口抽象 + 轻量实现**替代，接口形状保持与目标栈一致，切换时只换 Adapter，不动领域/应用层。

| 能力 | 目标栈 | 阶段 0/1 轻量实现 | 切换点 |
|------|--------|-------------------|--------|
| 关系数据库 | MySQL 8 | SQLite（SQLAlchemy，URL 配置切换） | 改 `DATABASE_URL` + Alembic |
| 异步队列 | Celery + Redis | 进程内 `TaskRunner`（asyncio/BackgroundTasks） | 换 `TaskRunner` 的 Celery 实现 |
| LLM | DeepSeek API | LangChain `ChatOpenAI`（DeepSeek 端点）+ `FakeLLM` | 配置 `LLM_PROVIDER` |
| 向量检索 | Milvus | 阶段 3 才需要，预留 `VectorStorePort`（本地可用 numpy/内存实现） | 换 Milvus Adapter |
| Embedding | 通义/BGE | 阶段 3 才需要，预留 `EmbeddingPort` | 同上 |
| 会话记忆 | Redis | 内存 dict（`MemoryPort`） | 换 Redis Adapter |

**原则**：领域层只依赖 `Port`（Protocol），不依赖具体 Adapter；Adater 在 `shared/infrastructure/*` 下实现，通过依赖注入装配。

## 7. 阶段 0 详细设计

### 7.1 目录结构（与技术设计说明书 3.5 一致）

```
ai-assistant-platform/
├── pyproject.toml               # 依赖与工具链（pip + venv，无 uv）
├── .env.example                 # 配置样例（LLM key 等）
├── README.md
├── alembic/                     # 迁移
├── shared/
│   ├── common/
│   │   ├── util/                # StringUtil, JsonUtil, DateUtil
│   │   └── exception/           # 统一异常体系 + 错误码
│   └── infrastructure/
│       ├── llm/                 # LangChain 封装（DeepSeek + FakeLLM）
│       ├── db/                  # SQLAlchemy session/engine（SQLite 默认）
│       ├── memory/              # 会话记忆（内存实现）
│       ├── observability/       # structlog + traceId + token 统计
│       └── tool_registry/       # 工具注册
├── contexts/
│   ├── sales_assistant/         # 营销（阶段2填充）
│   ├── teaching_assistant/      # 助教（阶段3填充）
│   ├── course_assistant/        # 课程（阶段4填充）
│   ├── exam_paper_generation/   # 出题（阶段1填充）
│   ├── self_practice/           # 自主练习（阶段1填充）
│   ├── exam_grading/            # 批改（阶段1填充）
│   └── learning_analytics/      # 学情（阶段5）
├── orchestrator/                # 意图路由骨架
├── api/                         # FastAPI 路由 + 统一响应 + 异常处理
└── tests/                       # pytest
```

每个 context 内部按 `domain/`、`application/`、`infrastructure/` 分层（阶段 0 先建空骨架 + `__init__.py`，阶段 1 起填充）。

### 7.2 阶段 0 交付项清单

1. **工程**：`git init` + `pyproject.toml` + `.gitignore` + `.env.example` + `README.md`；创建 `.venv` 并安装依赖。
2. **shared/common**：`util` 三个工具类；`exception` 统一异常基类 + 业务错误码枚举。
3. **shared/infrastructure/llm**：`LLMClient` 封装（`chat()` / `chat_json()`，带重试+超时+token 计量）；`DeepSeekAdapter`（`ChatOpenAI` 指向 DeepSeek 端点）+ `FakeLLMAdapter`（测试用）。
4. **shared/infrastructure/db**：`Base` + `session_factory` + 连接配置（默认 SQLite 文件）。
5. **数据模型 + 迁移**：按技术设计 6.2 定义全部表（同步缓存表 + 业务表）的 SQLAlchemy 模型，Alembic 初始迁移。
6. **shared/infrastructure/memory**：`MemoryPort` + 内存实现。
7. **shared/infrastructure/observability**：structlog 配置 + traceId 中间件 + token 计数占位。
8. **shared/infrastructure/tool_registry**：`@tool` 注册表（按 context 命名空间隔离）。
9. **api**：FastAPI app、统一响应 `{code,message,data,traceId}`、全局异常处理器、`/health` `/ready`。
10. **orchestrator**：路由骨架（阶段 0 空实现，阶段 2+ 接 Agent 图）。
11. **依赖规则检查**：`import-linter` 或等价脚本，断言 `contexts/* → shared/infrastructure → shared/common` 单向、context 间无直接依赖。
12. **测试基架**：pytest + 冒烟测试（health、配置加载、模型可建表）。

### 7.3 阶段 0 明确不做

- 任何 Agent 业务逻辑与 LangGraph 图（阶段 1 起）。
- Milvus / Embedding / Celery 接入（阶段 3 / 按需）。
- 真实 MySQL/Redis（SQLite + 内存替代）。

## 8. 留给实施者的自由度

- 依赖管理细节（pip + venv 的具体锁定版本）、代码内命名与模块切分粒度。
- 表模型是否拆多文件（阶段 0 为可读性按域拆文件，最终以 Alembic 迁移为准）。
- 阶段 0 中"全量表"若发现某表完全用不到，可推迟到其所属阶段再建（但仍保持 Alembic 顺序可追溯）。

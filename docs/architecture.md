# 码帮智 · 教育智能体平台 — 架构说明

> 本文档描述当前代码库的架构、模块划分与领域之间的依赖关系。
> 领域（bounded context）的详细说明见各 `contexts/<name>/README.md`。

## 1. 概述

平台是一个**后端 AI 智能体中台**，覆盖「售前获客 → 课程匹配 → 课后答疑 → 自主练习 → 学情分析」全链路。采用 **DDD（限界上下文）+ 端口与适配器（Ports & Adapters）** 架构，模块化单体起步，通过接口隔离，某个上下文负载或团队需要时再拆微服务。

**技术栈**：Python 3.13 / FastAPI / SQLAlchemy 2.x / Pydantic v2 / DeepSeek（可注入 Mock）/ SQLite（默认，可切 MySQL）。

## 2. 分层架构

上下文内部**按需采用 2~4 层**：标准上下文四层齐全；生产者上下文（`exam_paper_generation`、`exam_grading`）只有 domain + infrastructure 两层（见 §4/§5）。标准四层的依赖方向从外向内，**domain 层不依赖任何外层**：

```mermaid
graph TB
    subgraph ctx["一个标准上下文（四层）"]
        I["interface 接口层<br/>REST 路由 / schemas / 依赖装配"]
        A["application 应用层<br/>用例编排（service）"]
        D["domain 领域层<br/>业务规则 + 端口(Protocol)"]
        IN["infrastructure 基础设施层<br/>端口适配器 / 仓储"]
    end

    I --> A
    I --> IN
    A --> D
    IN --> D
```

> 依赖倒置：application 与 infrastructure **都**依赖 domain 的端口（Protocol），二者互不 import。interface 是组合根，同时装配 application 与 infrastructure 的具体实现。

| 层 | 职责 | 依赖方向 |
|----|------|---------|
| **interface** | 对外入口（FastAPI 路由）、请求模型、依赖注入装配（组合根） | → application + infrastructure |
| **application** | 用例编排，不落具体技术细节 | → domain（含端口） |
| **domain** | 纯业务规则、端口协议（Protocol）、领域类型 | 不依赖任何外层 |
| **infrastructure** | 端口适配器、仓储、LLM/DB/消息等具体实现 | → domain（实现其端口） |

**依赖规则**（由 `.importlinter` 强制执行）：

- `shared` 不依赖 `contexts` / `orchestrator` / `api`
- 叶子上下文互相独立
- 生产者上下文只允许依赖 `self_practice` 的端口

## 3. 顶层模块

```
ai-assistant-platform/
├── api/                     # FastAPI 外壳：create_app、路由挂载、异常处理、健康检查
├── contexts/                # 6 个限界上下文（业务领域）
├── orchestrator/            # 意图路由骨架（当前为空占位）
├── shared/                  # 共享基础设施（纯技术能力）
│   ├── common/              #   exception（统一异常/错误码）、util
│   └── infrastructure/      #   config、db、llm、memory、observability、tool_registry、web
└── docs/                    # 规格 / 计划 / 本文档
```

### shared 基础设施清单

| 模块 | 职责 |
|------|------|
| `config` | 环境配置（`get_settings`） |
| `db` | `Base` / `utcnow`、session、SQLAlchemy 模型（见 §6） |
| `llm` | `LLMPort` 协议、DeepSeek 适配器、`FakeLLMAdapter`（测试）、`get_llm` 工厂 |
| `memory` | `MemoryPort` 协议 + 内存实现（会话状态） |
| `observability` | structlog 日志、traceId 中间件 |
| `tool_registry` | 工具注册表（按 context 命名空间隔离） |
| `web` | 统一响应 `ApiResponse` + `ok()` |

## 4. 上下文清单

| 上下文 | Agent | 定位 | 分层 | 对外 API |
|--------|-------|------|------|---------|
| `sales_assistant` | 营销 Agent | 智能客服 / 线索留资 | 4 层 | `/api/v1/sales/*` |
| `teaching_assistant` | 助教 Agent | 答疑 RAG / 转人工 | 4 层 | `/api/v1/teaching/*` |
| `learning_analytics` | 学情分析 Agent | 画像 / 趋势 / 薄弱点 | 4 层 | `/api/v1/analytics/*` |
| `self_practice` | 自主练习 Agent | **编排者**：练习闭环 | 4 层 | `/api/v1/practice/*` |
| `exam_paper_generation` | 出题 Agent | 生产者：出题 | 2 层（无 interface/application） | 无 |
| `exam_grading` | 评价 Agent | 生产者：批改 | 2 层（无 interface/application） | 无 |

> 出题与批改为「生产者」上下文，仅被 `self_practice` 通过端口调用，不对外暴露 API，因此省略 interface 与 application 两层。

## 5. 领域依赖关系

```mermaid
graph TB
    subgraph api["api 层"]
        API["api/main.py<br/>挂载各上下文 router"]
    end

    subgraph leaf["叶子上下文（互相独立）"]
        sales["sales_assistant<br/>营销/客服"]
        teaching["teaching_assistant<br/>助教/答疑RAG"]
        analytics["learning_analytics<br/>学情分析"]
        practice["self_practice<br/>自主练习·编排者"]
    end

    subgraph producer["生产者上下文（仅依赖 self_practice 端口）"]
        gen["exam_paper_generation<br/>出题"]
        grading["exam_grading<br/>批改"]
    end

    SHARED["shared<br/>共享基础设施"]

    API --> sales
    API --> teaching
    API --> analytics
    API --> practice

    gen -->|import 端口| practice
    grading -->|import 端口| practice

    sales --> SHARED
    teaching --> SHARED
    analytics --> SHARED
    practice --> SHARED
    gen --> SHARED
    grading --> SHARED
```

**依赖规则解读：**

1. **所有上下文都依赖 `shared`**（LLM、DB、统一响应、日志等纯技术能力）。
2. **`api` 依赖所有上下文的 `interface` 路由**，是唯一把各领域装配起来的地方。
3. **四个叶子上下文互相独立**（`sales / teaching / analytics / self_practice` 之间不 import）。
4. **出题 / 批改是「生产者」**：单向依赖 `self_practice.domain.ports`（import `Question` / `GradeResult` / 端口协议），但不依赖任何叶子上下文。`self_practice` 反过来不知道它们的存在。

## 6. 端口与适配器（自主练习闭环）

`self_practice` 是编排者，在**自己的 domain 里定义它需要的端口**（消费者驱动契约），出题 / 批改上下文各自实现这些端口，运行时通过依赖注入装配：

```mermaid
graph LR
    PS["PracticeService<br/>(self_practice 应用层)"]
    QP["QuestionGenerationPort<br/>(定义在 self_practice.domain.ports)"]
    GP["GradingPort<br/>(定义在 self_practice.domain.ports)"]
    QGA["QuestionGenerationAdapter<br/>(exam_paper_generation)"]
    GA["GradingAdapter<br/>(exam_grading)"]
    LLM["LLMPort"]

    PS --> QP
    PS --> GP
    QGA -.实现.-> QP
    GA -.实现.-> GP
    QGA --> LLM
    GA --> LLM
```

- `PracticeService` 只认 `QuestionGenerationPort` / `GradingPort` 两个协议，不 import 具体适配器。
- 具体适配器在 `self_practice/interface/dependencies.py` 注入（组合根），是唯一把三者连起来的地方。
- 好处：删除 `exam_paper_generation` / `exam_grading` 目录，`self_practice` 的 domain / application 不受影响，只有 `dependencies.py` 一处 import 报错。

**运行时调用链**：`self_practice` →（通过端口）→ 出题 / 批改 → `LLMPort`；结果回流 `self_practice` 持久化，供 `learning_analytics` 下游消费。

## 7. 数据模型分组

`shared/infrastructure/db/models/` 下分两组：

| 分组 | 文件 | 表 | 用途 |
|------|------|-----|------|
| **同步缓存** | `sync_cache.py` | `course` / `chapter` / `video` / `video_annotation` / `student` / `student_course` / `student_video_progress` | 从外部系统同步的只读参考数据 |
| **业务** | `business.py` | `lead` / `practice_session` / `practice_question` / `practice_answer` | 本平台自身产生的业务数据 |

## 8. 运行时装配

- `api/main.py::create_app()` 注册 TraceId 中间件、异常处理器、健康检查与 4 个业务上下文的 router。
- 每个上下文在 `interface/dependencies.py` 用 FastAPI `Depends` 装配 service，注入 `LLMPort` 与各端口适配器。
- 测试用 `sqlite://` 内存库 + `FakeLLMAdapter` + `app.dependency_overrides` 覆盖依赖。

## 9. 相关文档

- 需求规格说明书：`docs/码帮智 · 教育智能体平台需求规格说明书.md`
- 技术设计说明书：`docs/码帮智 · 教育智能体平台系统技术设计说明书.md`
- 分阶段实施设计：`docs/superpowers/specs/2026-11-17-implementation-phasing-design.md`
- 依赖规则配置：`.importlinter`

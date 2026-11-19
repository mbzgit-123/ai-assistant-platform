# 阶段 4 — 课程 Agent + 督学 设计

- 日期：2026-11-18
- 上游文档：《需求规格说明书》V1.0（FR-006/007/009）、《分阶段实施设计》（阶段 4）
- 上游已批准：分阶段实施设计把阶段 4 定为「课程 Agent + 督学」，覆盖 FR-006 学习路径规划、FR-007 学习计划落地与调整、FR-009 智能督学。本设计只补充阶段 4 内部的「怎么做」，不重复已批准的整体架构。

## 1. 意图

给已购课/VIP 学员交付三个能力：按岗位方向生成个性化学习计划（FR-006）；计划绑定真实课程/章节 ID、随学习进度动态重规划（FR-007）；监测学习时长/进度、异常时通过短信/微信通道触达提醒（FR-009）。

## 2. 目标 / 非目标 / 反目标

**目标**
- 在 `contexts/course_assistant/` 内落地 FR-006/007/009，产出可运行、可测试的增量。
- 复用已建立的端口 + 轻量适配器模式，切换真实中间件只换 Adapter。

**非目标（本阶段不做）**
- 真实短信/微信网关、真实 Celery/Redis 定时调度（端口预留，Adapter 留空/存根）。
- 学情分析（阶段 5，`learning_analytics`）。
- 前端界面。

**反目标（做了即算失败）**
- 破坏 DDD 依赖规则（context 间直接依赖、shared 依赖 context）。
- 学习计划的「顺序」交给 LLM 决定（顺序必须确定性，LLM 只生成内容文案）。
- 为「本地轻量」写死 SQLite 或写死短信通道。

## 3. 约束

- 技术栈同阶段 0：Python 3.13、FastAPI、SQLAlchemy 2.x、Pydantic v2、structlog、pytest。
- 依赖规则：`contexts/course_assistant` 只依赖 `shared` + 自身；接口层在 `contexts/course_assistant/interface/`，不进顶层 `api/`。
- LLM 端口：`LLMPort.chat(messages) -> LLMResult(content)`（纯文本，无 JSON 模式）。

## 4. 关键决策（approaches 与选定）

| 决策点 | 候选 | 选定 | 理由 |
|--------|------|------|------|
| 岗位→课程路径知识库 | ① 新建 DB 表（PositionPath / CoursePrerequisite）② 领域端口 + 内存知识库 | **② 端口 + 内存实现** | 路径顺序与前置依赖是人工策划的少量数据；`course` 表已带 `position`。内存实现最简、可测、后续可换 DB Adapter。不新建表（YAGNI）。 |
| 督学调度 | ① 真实 Celery/APScheduler ② 端口 + 显式触发端点 | **② 显式端点触发** | v1.0 无真实定时中间件（分阶段设计 §6 已定「进程内 TaskRunner」为轻量替代）。把「定时」外置为幂等端点，外部 cron/Celery 到时调用即可；短信通道走 `MessageChannelPort`。 |
| 学习计划持久化 | ① 新建 LearningPlan 表 ② 无状态按需重算 | **② 无状态重算** | 计划始终由「当前进度 + 知识库」推导，天然满足 FR-007「进度变化动态重规划」，无脏快照问题。绑定 ID 在返回体中携带。 |

## 5. 已定「怎么做」

### 5.1 目录与职责（`contexts/course_assistant/`）

- `domain/positions.py`：岗位常量 `POSITIONS = ("Java 开发岗", "大模型算法岗", "大模型应用开发岗")`。
- `domain/path.py`：`PathStep(course_id, chapter_ids, is_foundation)`、`LearningPlan(position, steps)` 领域对象。
- `domain/ports.py`：`PathKnowledgePort.get_path(position) -> list[PathStep]`、`MessageChannelPort.send(student_id, content) -> str`、`ProgressPort`（读已学进度）。
- `infrastructure/path_knowledge.py`：`InMemoryPathKnowledge`（策划好的岗位→有序课程序列 + 前置依赖 + `is_foundation` 标记）。
- `infrastructure/message_channel.py`：`StubMessageChannel`（记录并返回消息 id，同阶段 3 `StubHandoff` 模式）。
- `infrastructure/repository.py`：`CourseRepository`（读 `Student`、`StudentCourse`、`StudentVideoProgress`、`Course`、`Chapter`）。
- `application/service.py`：`CourseAssistantService`（`generate_plan` / `replan`）+ `SupervisionService`（`check_and_notify`）。
- `interface/schemas.py`、`interface/routes.py`、`interface/dependencies.py`：API 装配。

### 5.2 学习计划生成（FR-006）

- 输入：`position` + `student_id`。从 `Student` 读 `education`/`major` 判定「零基础 / 有基础」。
- 顺序 = 确定性：`PathKnowledgePort.get_path(position)` 返回有序步骤（已编码前置依赖）。LLM **不**决定顺序。
- 基础调整：有基础 → 跳过 `is_foundation=True` 的前置步骤；零基础 → 保留。
- LLM 只生成每步「学习内容」文案（用 `course.name`/`highlights` 组织）；LLM 失败时确定性兜底（用课程名/亮点拼文案）。
- 输出：`LearningPlan`，每步带真实 `course_id` + `chapter_ids`（绑真实章节，供前端跳转）。

### 5.3 动态重规划（FR-007）

- `replan(student_id)`：读 `StudentVideoProgress` 求已学完的 course_id 集合 → 从计划中剔除 → 返回剩余有序计划。
- 无新表；进度来源即 `student_video_progress.completed_at`。

### 5.4 智能督学（FR-009）

- `MessageChannelPort.send(student_id, content)`：短信/微信通道抽象，`StubMessageChannel` 记录并返回 `msg_<id>`。
- `SupervisionService.check_and_notify(session)`：对每个已购课学员计算（a）距上次完课天数、（b）整体进度比；命中阈值则发送提醒。
- 阈值（本设计拍板，规格未给具体值）：
  - 距上次完课 ≥ 3 天 → 提醒（`提醒继续学习`）。
  - 距上次完课 ≥ 7 天 → 升级提醒（`已一周未学习`）。
  - 有剩余计划但无新完课记录视为「进度停滞」，同样触发。
- 触发：`POST /api/v1/course/supervision/check`（幂等），外部定时器到时调用；v1.0 不内置调度循环。

### 5.5 API 面（`interface/routes.py`，prefix `/api/v1/course`）

- `POST /plan`：`{position, studentId}` → 学习计划。
- `POST /plan/refresh`：`{studentId}` → 重规划后的剩余计划。
- `POST /supervision/check`：运行督学检查 → 返回本次发出的通知列表。

`api/main.py` 增加 `app.include_router(course_router)`。

## 6. 留给实施者的自由度

- 内存知识库里各岗位的具体课程序列与 `course_id` 命名（测试用策划值即可）。
- 阈值常量命名与放置位置（建议 `domain/supervision.py` 集中）。
- 测试夹具的组织方式（沿用既有 `tests/contexts/course_assistant/` 命名防冲突约定）。

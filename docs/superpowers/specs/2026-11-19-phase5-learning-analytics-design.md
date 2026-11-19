# 阶段 5 — 学情分析（learning_analytics）设计

- 日期：2026-11-19
- 上游文档：《需求规格说明书》G-06、《系统技术设计说明书》§5.7、《分阶段实施设计》阶段 5
- 状态：已确认（对话中拍板，本文档为决策留档）

## 1. 意图

给教师/教研交付学情分析能力（G-06）：长期学习画像、掌握度趋势、薄弱点归因。学情分析是第一个「下游消费者」——自己不产生数据，从既有的练习、批改、视频进度数据聚合而来。

## 2. 目标 / 非目标

**目标**
- 在 `contexts/learning_analytics/` 内落地 G-06 三项能力，产出可运行、可测试增量。
- 复用端口 + 轻量适配器模式；统计聚合确定性，归因解释用 LLM（带确定性兜底）。

**非目标（本阶段不做）**
- 事件总线 / 领域事件订阅（阶段 0 仅「预留」）。学情分析只读共享表，不订阅事件。
- 写 `learning_profile` / `mastery_trend` / `weak_point` 三张表（阶段 0 已建，本阶段留空不用；将来接 Kafka 异步流水线时再填）。
- 真实权限控制（教师/教研鉴权）、前端。

**反目标（做了即算失败）**
- 破坏 DDD 依赖规则（context 间直接依赖、shared 依赖 context）。
- 引入事件总线或写表，把本阶段从「只读聚合」变成「异步管道」。

## 3. 约束

- 技术栈同阶段 0：Python 3.13、FastAPI、SQLAlchemy 2.x、Pydantic v2、structlog、pytest。
- 依赖规则：`contexts/learning_analytics` 只依赖 `shared` + 自身；接口层在 `contexts/learning_analytics/interface/`。
- LLM 端口：`LLMPort.chat(messages) -> LLMResult(content)`（纯文本，无 JSON 模式）。

## 4. 关键决策（approaches 与选定）

| 决策点 | 候选 | 选定 | 理由 |
|--------|------|------|------|
| 数据流 | ① 事件驱动（DomainEventBus + 订阅）② 直接聚合（只读共享表） | **② 直接聚合** | 用户拍板；最简、不新建事件总线、不碰其它 context；与阶段 4「无状态按需重算」一致。事件总线是 v1.1 接 Kafka 的事。 |
| 三张学情表 | ① 写表 + 刷新触发 ② 留空不用，按需现算 | **② 留空不用** | 与「直接聚合」一致；写表是 v1.1 异步流水线。表已存在但本阶段不读不写。 |
| 能力范围 | ① 三项全做 ② 先做画像 | **① 三项全做** | G-06 列全，源数据都支持，无拆分必要。 |

## 5. 已定「怎么做」

### 5.1 目录与职责（`contexts/learning_analytics/`）

- `domain/analysis.py`：领域对象 `Profile`、`MasteryTrendPoint`、`WeakPoint`、`StudentAnalysis`（含三者 + `to_dict()`）。
- `domain/ports.py`：`LearningDataPort`（读练习/进度/课程的聚合数据）。
- `infrastructure/repository.py`：`LearningRepository(session)` 实现端口，读 `PracticeAnswer` / `PracticeQuestion` / `Video` / `Chapter` / `Student` / `StudentCourse` / `StudentVideoProgress`。
- `application/service.py`：`LearningAnalyticsService.analyze(student_id) -> StudentAnalysis`（统计确定性 + LLM 归因）。
- `interface/schemas.py`、`routes.py`、`dependencies.py`：API 装配。

### 5.2 画像（profile）

从 `Student` + `StudentCourse` + `StudentVideoProgress` + `PracticeAnswer` 聚合：在学课程数、视频完成度、整体正确率、主观题均分、最近活跃时间。

### 5.3 掌握度趋势（trend）

`PracticeAnswer` 按 `video_id`（经 `PracticeQuestion` 归到章节）分桶，按 `answered_at` 时间排序，产出「章节 × 时间桶 → 正确率」的时间序列。掌握度 v1.0 以正确率为代理指标。

### 5.4 薄弱点归因（weak_points）

确定性统计：按章节算正确率，取最低的若干（或低于阈值者）。对每个薄弱点调 `LLMPort` 生成「为什么弱 + 建议」，LLM 失败时用确定性兜底文案。

### 5.5 API

- `GET /api/v1/analytics/student/{studentId}` → `{profile, trend, weakPoints}`。

`api/main.py` 增加 `app.include_router(analytics_router)`。

## 6. 留给实施者的自由度

- 趋势的时间分桶粒度（建议按天/周）、归因的阈值/取数（建议正确率 < 60% 或取最低 3 个）。
- 领域对象字段命名与 `to_dict()` 序列化形状。
- 测试夹具组织（沿用 `tests/contexts/learning_analytics/` 命名约定）。

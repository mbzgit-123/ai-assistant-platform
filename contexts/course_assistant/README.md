# course_assistant（智能课程 / 学习路径规划 + 督学）

面向**课程匹配与学习规划**的课程 Agent，以及**过程督学**的定时触达能力：按岗位生成学习路径，并根据学习进度重排；对久未学习的学员发送提醒/升级触达。

## 职责

- 学习路径规划：按岗位方向查路径知识库生成学习计划，有基础（已有专业）的学员自动跳过基础课
- 路径重排（refresh）：排除已完成课程，输出剩余计划
- 督学检测：遍历在读学员，按"距上次完成天数"分级（提醒 / 升级）并发送消息

## 分层结构

```
contexts/course_assistant/
├── domain/
│   ├── path.py         # PathStep / LearningPlan / PlanItem
│   ├── positions.py    # 岗位方向定义
│   ├── supervision.py  # 督学阈值与话术（提醒/升级天数）
│   └── ports.py        # PathKnowledgePort / MessageChannelPort / ProgressPort
├── application/
│   └── service.py      # CourseAssistantService + SupervisionService
├── infrastructure/
│   ├── path_knowledge.py  # 路径知识库适配器
│   ├── message_channel.py # 消息通道适配器
│   └── repository.py      # 学员/课程进度读取
└── interface/
    ├── routes.py       # REST 路由
    ├── schemas.py      # 请求模型
    └── dependencies.py # 依赖装配
```

## 端口

- **定义（对外提供）**：`PathKnowledgePort.get_path`、`MessageChannelPort.send`、`ProgressPort`（get_profile / completed_course_ids / enrolled_student_ids / last_completed_at / get_course_title）
- **消费（依赖）**：`LLMPort`

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/course/plan` | 生成学习路径 |
| POST | `/api/v1/course/plan/refresh` | 重排（排除已完成） |
| POST | `/api/v1/course/supervision/check` | 督学检测并发送触达 |

## 依赖

- 仅依赖 `shared`
- 与其他 context 无依赖（`contexts-leaf-independent` 契约）

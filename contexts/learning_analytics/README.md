# learning_analytics（学情分析）

面向**学情分析**场景的分析 Agent：聚合学员的学习画像、掌握度趋势与薄弱点归因，作为自主练习/批改闭环的下游消费者。

## 职责

- 学习画像：在读课程数、已完成/总视频数、整体正确率、主观题平均分、最近活跃时间
- 掌握度趋势：按"章节 + 日期"分桶计算正确率，输出时间序列
- 薄弱点归因：对正确率低于阈值的章节，用 LLM 给出一句话归因（失败回退确定性文案）
- 主观题范围：仅 `short_answer` / `scenario` 计入主观题平均分（确定性题型不参与）

## 分层结构

```
contexts/learning_analytics/
├── domain/
│   ├── analysis.py     # Profile / MasteryTrendPoint / WeakPoint / StudentAnalysis
│   └── ports.py        # LearningDataPort + AnswerRecord
├── application/
│   └── service.py      # LearningAnalyticsService
├── infrastructure/
│   └── repository.py   # LearningDataPort 适配器（读作答/进度）
└── interface/
    ├── routes.py       # REST 路由
    └── dependencies.py # 依赖装配
```

## 端口

- **定义（对外提供）**：`LearningDataPort`（enrolled_course_count / completed_video_count / enrolled_video_count / answer_records / last_completed_at）
- **消费（依赖）**：`LLMPort`

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/analytics/student/{studentId}` | 返回学员画像 + 趋势 + 薄弱点 |

## 依赖

- 仅依赖 `shared`
- 与其他 context 无依赖（`contexts-leaf-independent` 契约）
- 数据来源为 `PracticeAnswer` 等业务表，通过端口读取，不反向依赖 `self_practice`

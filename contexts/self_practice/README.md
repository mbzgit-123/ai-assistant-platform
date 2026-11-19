# self_practice（自主练习 / 编排者）

面向**自主练习**闭环的**编排者上下文**：管理练习会话、按视频触发出题、合并多视频题目、判分批改、持久化并回填历史与学情。它是出题（`exam_paper_generation`）与批改（`exam_grading`）的调用方，通过端口解耦。

## 职责

- 已学视频展示：只列出已完成学习的视频
- 时长准入：累计时长 `<30` 拦截、`30–60` 软提示（需 `confirm=true`）、`60–90` 放行、`>90` 拦截
- 出题编排：复用已有题目（打乱顺序）或调用出题端口新生成（`regenerate=true` 强制重生成）
- 多视频合并：合并多视频题量并封顶总上限
- 提交判分：逐题判分（确定性 + LLM），回填作答、标记会话已提交
- 练习历史：按时间倒序列出历史会话

## 分层结构

```
contexts/self_practice/
├── domain/
│   ├── admission.py    # 时长准入（4 档）
│   ├── merge.py        # 多视频题量合并封顶
│   └── ports.py        # QuestionGenerationPort / GradingPort + Question / GradeResult
├── application/
│   └── service.py      # PracticeService（编排者）
├── infrastructure/
│   └── repository.py   # PracticeRepository（会话/题目/作答持久化）
└── interface/
    ├── routes.py       # REST 路由
    ├── schemas.py      # 请求模型
    └── dependencies.py # 依赖装配（注入出题/批改适配器）
```

## 端口

- **定义（对外提供）**：`QuestionGenerationPort`（plan_counts / generate_by_video）、`GradingPort`（grade），以及领域类型 `Question`、`GradeResult`
- **消费（依赖）**：上述两个端口（由 `exam_paper_generation` / `exam_grading` 实现）

> 注意：这两个端口是"消费者驱动契约"——`self_practice` 在自己 domain 里定义它需要的接口，出题/批改上下文去适配。`self_practice` 本身不 import 那两个上下文。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/practice/available-videos` | 已学视频列表 |
| POST | `/api/v1/practice/start` | 发起练习（准入 + 出题） |
| POST | `/api/v1/practice/submit` | 提交作答（判分） |
| GET | `/api/v1/practice/history` | 练习历史 |
| GET | `/api/v1/practice/{practiceId}` | 单次练习结果 |

## 依赖

- 依赖 `shared`
- 依赖两个端口（运行时注入 `exam_paper_generation` / `exam_grading` 的适配器，但**不 import 它们**）
- 与其他叶子 context 无依赖（`contexts-leaf-independent` 契约）

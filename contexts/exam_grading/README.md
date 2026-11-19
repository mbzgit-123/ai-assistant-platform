# exam_grading（智能批改 / 评价）

面向**批改**场景的**生产者上下文**：对题目作答判分。确定性题型（不定项选择、代码填空）走纯代码判分，主观题（简答、场景）走 LLM 批改。它实现 `self_practice` 定义的 `GradingPort` 端口。

## 职责

- 不定项选择判分：所选集合与正确集合完全一致才得分（0/1）
- 代码填空判分：逐空位去首尾空白精确比对，按"正确空位数 / 总空位数"给分
- 主观题批改：拼装题目+参考答案+作答，调 LLM 输出 `is_correct / score / feedback`，坏 JSON 重试一次后转人工
- rubric 命中：统计参考答案要点在作答中的命中条数

## 分层结构

```
contexts/exam_grading/
├── domain/
│   └── grading.py      # grade_multi_choice / grade_code_fill / rubric_hits
└── infrastructure/
    └── adapter.py      # GradingAdapter（实现 GradingPort，dispatch 题型）
```

> 无 `application` 层：批改是纯能力，编排逻辑在 `self_practice` 的应用层。
> 无 `interface` 层：不对外暴露 API，仅被 `self_practice` 通过端口调用。

## 端口

- **实现**：`GradingPort.grade(question, answer_content)`（定义在 `self_practice.domain.ports`）
- **消费（依赖）**：`LLMPort`

## API 端点

无（叶子上下文，不对外暴露）。

## 依赖

- 依赖 `shared`
- **单向依赖 `self_practice.domain.ports`**（import `Question`、`GradeResult` 类型）——`practice-producers-one-way` 契约允许生产者依赖 self_practice 端口，但禁止依赖其他叶子 context

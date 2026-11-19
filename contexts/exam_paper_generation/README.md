# exam_paper_generation（智能出题）

面向**出题**场景的**生产者上下文**：按视频锚点截取课件内容，用确定性规则计算题量、分配题型，再调用 LLM 生成题目。它实现 `self_practice` 定义的 `QuestionGenerationPort` 端口。

## 职责

- 锚点截取：按 `startSentence`/`endSentence`（或 fallback 区间）从章节 Markdown 截取视频对应内容
- 题量映射：按时长区间确定性映射单视频题量
- 题型分配：三必出题型（不定项选择/简答/场景）各 ≥1，代码填空约 30%（仅在含 >10 行代码块时出现）
- 出题生成：按题型 schema + prompt 调 LLM 生成，坏 JSON 重试一次后丢弃
- 代码填空题特殊约束：挖核心部分（非整段覆盖）、`______` 占位、`answers` 按顺序列出挖空内容

## 分层结构

```
contexts/exam_paper_generation/
├── domain/
│   ├── allocation.py   # 题型分配
│   ├── anchor.py       # 锚点截取 / 代码块检测 / 超长截断
│   └── count.py        # 题量映射
└── infrastructure/
    └── adapter.py      # QuestionGenerationAdapter（实现 QuestionGenerationPort）
```

> 无 `application` 层：出题是纯能力，编排逻辑（何时生成/复用）在 `self_practice` 的应用层。
> 无 `interface` 层：不对外暴露 API，仅被 `self_practice` 通过端口调用。

## 端口

- **实现**：`QuestionGenerationPort.plan_counts / generate_by_video`（定义在 `self_practice.domain.ports`）
- **消费（依赖）**：`LLMPort`、`shared` 同步缓存模型（Video/Chapter/VideoAnnotation）

## API 端点

无（叶子上下文，不对外暴露）。

## 依赖

- 依赖 `shared`
- **单向依赖 `self_practice.domain.ports`**（import `Question` 类型）——`practice-producers-one-way` 契约允许生产者依赖 self_practice 端口，但禁止依赖其他叶子 context

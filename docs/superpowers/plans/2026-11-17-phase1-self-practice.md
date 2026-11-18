# 阶段 1 — 自主练习闭环（出题 + 练习 + 批改）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现自主练习闭环：按已学视频发起练习（准入校验 + 锚点截取出题 + 题量/题型确定性计算 + 题目复用），提交后选择题自动判分、主观题/代码题调批改 Agent，结果持久化并返回。

**Architecture:** 三个限界上下文协作：`exam_paper_generation`（出题：截取/题量/题型确定性 + LLM 生成）、`self_practice`（编排者：准入校验、题目复用、多视频合并、会话/作答持久化）、`exam_grading`（批改：选择题确定性判分 + 主观题 rubric+LLM）。跨上下文通过 **端口（Port）+ 依赖倒置** 交互：`self_practice/domain/ports.py` 定义 `QuestionGenerationPort` / `GradingPort` 协议及 `Question` / `GradeResult` DTO，两个生产方上下文（`exam_paper_generation`、`exam_grading`）的 infrastructure 层实现该协议（依赖倒置：生产方 import 编排方的抽象），装配在 `api` 组合根完成。确定性逻辑（截取/题量/题型/准入/判分）全部为纯函数，LLM 只做题目内容生成与主观题反馈解释。

**Tech Stack:** 复用阶段 0 的 Python 3.13.5、FastAPI、SQLAlchemy 2.x、Pydantic v2、`shared.infrastructure.llm`（DeepSeek/Fake）、pytest。不引入新依赖。

**Spec:**
- `docs/superpowers/specs/2026-11-17-implementation-phasing-design.md`（阶段 1 交付物：第 5 节表格第 47 行）
- `docs/码帮智 · 教育智能体平台需求规格说明书.md`（8.3 自主练习模块 FR-010~020、9.1.4 自主练习规则、10.2 主流程、11.4 异常清单、14.2 数据字段、15.1 接口、17 验收）
- `docs/码帮智 · 教育智能体平台系统技术设计说明书.md`（5.4~5.6 三个 Agent、6.2 业务表、7.2 对外 API、7.4 内部端口、8.3 主流程）

## Global Constraints

- Python 版本 ≥ 3.11（本机 3.13.5）；所有命令在 venv 内执行：`source .venv/Scripts/activate && <cmd>`（或用 `.venv/Scripts/python.exe -m` 直接调用）。
- 依赖方向严格单向：`contexts/* → shared/infrastructure → shared/common`；`shared` 不得依赖 `contexts/orchestrator/api`。
- 统一响应结构 `{"code": int, "message": str, "data": Any, "traceId": str}`，成功 `code = 0`。
- LLM 默认 `fake`（`Settings.llm_provider` 默认值），测试/无 key 环境不得连真实 DeepSeek。
- 确定性逻辑（截取/题量/题型/准入/判分）必须为**纯函数**，不得有 LLM/IO 副作用；LLM 只做题目生成与主观题反馈解释。
- v1.0 明确不做（需求文档第 18 节）：换一批、总题量上限优化、练习历史、软提示分级准入、学情分析接入。

## Review Focus

1. 锚点匹配失败时仅靠 `fallbackRange` 兜底，若 fallback 也解析不出内容，出题应干净降级（跳过该视频或提示重试），而不是抛 500 崩溃——测试：坏锚点 + 空 fallbackRange 的单视频出题不抛异常。
2. LLM 输出非 JSON 时（重试一次仍失败）应丢弃该题型并继续，整次练习不因单题型失败而中断——测试：FakeLLM 返回非法 JSON 的 adapter 调用返回部分题目而非抛异常。
3. 准入边界值：恰好 60 分钟（3600 秒）放行、3599 秒拦截——测试边界 ±1 秒。
4. 题目复用时不得再次调用 LLM，且复用题目顺序被打乱——测试：复用路径 FakeLLM 调用次数为 0。
5. 多视频合并「总题量上限 30」与「每视频保底 3」在视频数 >10 时冲突（保底和 > 上限）——`merge_counts` 需有明确降级，不抛异常、不出现负题量。

---

### Task 1: exam_paper_generation — 确定性出题规则（截取/代码块/题量/题型分配）

**Files:**
- Create: `contexts/exam_paper_generation/domain/__init__.py`
- Create: `contexts/exam_paper_generation/domain/anchor.py`
- Create: `contexts/exam_paper_generation/domain/count.py`
- Create: `contexts/exam_paper_generation/domain/allocation.py`
- Test: `tests/contexts/exam_paper_generation/test_generation_rules.py`

**Interfaces:**
- Produces（纯函数，无 IO、无跨上下文 import）：
  - `slice_content_md(content_md: str, start_sentence: str, end_sentence: str) -> str | None`：`find(start_sentence)` 定位起点，`find(end_sentence, start_idx)` 定位终点；均命中且 `start_idx <= end_idx` 时返回 `content_md[start_idx : end_idx + len(end_sentence)]`（含首尾句）；任一未命中返回 `None`。
  - `split_long_interval(text: str, max_chars: int = 2000) -> str`：`len <= max_chars` 原样返回；否则按行（`\n`）累加，累加到下一行会超过 `max_chars` 即停止，返回已累加部分（段落边界截断，不硬切）。
  - `has_code_block(text: str) -> bool`：`"```" in text`。
  - `count_for_duration(duration_seconds: int) -> int`：区间下限映射——`<300→3`、`300–899→5`、`900–1799→8`、`>=1800→10`（确定性取区间下限，作为单视频默认题量；区间上界仅作软性参考，FR-016 多视频合并时再按比例缩放）。
  - `allocate_types(total: int, has_code: bool) -> dict[str, int]`：返回 `{"choice", "short_answer", "scenario", "code"}` 四项且和为 `total`。算法（确定性，采用整除 `//`）：
    ```
    code = 0
    if has_code and total >= 4:
        code = min(4, total * 30 // 100) or 1   # 至少 1，封顶 4
        code = min(code, total - 3)              # 给三必出题型留位
    rest = total - code
    extra = rest - 3
    choice = 1 + extra * 4 // 9
    short_answer = 1 + extra * 3 // 9
    scenario = rest - choice - short_answer
    ```
    三必出题型（choice/short_answer/scenario）各至少 1；`total < 4` 时不生成代码题（即便有代码块，静默跳过）。

- [ ] **Step 1: 写失败测试**

`tests/contexts/exam_paper_generation/test_generation_rules.py`：

```python
from contexts.exam_paper_generation.domain.anchor import (
    slice_content_md, split_long_interval, has_code_block,
)
from contexts.exam_paper_generation.domain.count import count_for_duration
from contexts.exam_paper_generation.domain.allocation import allocate_types

def test_slice_content_md_hits_anchors():
    md = "标题\n段落A\n锚点首句X\n中间内容\n锚点尾句Y\n结尾"
    assert slice_content_md(md, "锚点首句X", "锚点尾句Y") == "锚点首句X\n中间内容\n锚点尾句Y"

def test_slice_content_md_start_missing_returns_none():
    assert slice_content_md("abc", "不存在", "c") is None

def test_slice_content_md_end_missing_returns_none():
    assert slice_content_md("abc start xyz", "start", "不存在") is None

def test_split_long_interval_short_unchanged():
    assert split_long_interval("短文本", max_chars=2000) == "短文本"

def test_split_long_interval_cuts_at_paragraph_boundary():
    text = "\n".join("段落" + str(i) for i in range(1000))  # > 2000 字符
    result = split_long_interval(text, max_chars=2000)
    assert len(result) <= 2000
    assert result.endswith(("段落0", "段落1", "段落2")) or result

def test_has_code_block():
    assert has_code_block("说明文字\n```python\nprint(1)\n```") is True
    assert has_code_block("纯文字无代码") is False

def test_count_for_duration_buckets():
    assert count_for_duration(0) == 3
    assert count_for_duration(299) == 3
    assert count_for_duration(300) == 5
    assert count_for_duration(899) == 5
    assert count_for_duration(900) == 8
    assert count_for_duration(1799) == 8
    assert count_for_duration(1800) == 10
    assert count_for_duration(3600) == 10

def test_allocate_types_no_code():
    assert allocate_types(3, False) == {"choice": 1, "short_answer": 1, "scenario": 1, "code": 0}

def test_allocate_types_code_present():
    assert allocate_types(4, True) == {"choice": 1, "short_answer": 1, "scenario": 1, "code": 1}
    assert allocate_types(10, True) == {"choice": 2, "short_answer": 2, "scenario": 3, "code": 3}
    assert allocate_types(15, True) == {"choice": 4, "short_answer": 3, "scenario": 4, "code": 4}

def test_allocate_types_no_code_big():
    assert allocate_types(15, False) == {"choice": 6, "short_answer": 5, "scenario": 4, "code": 0}

def test_allocate_types_sum_equals_total():
    for total in range(3, 31):
        for has_code in (False, True):
            d = allocate_types(total, has_code)
            assert sum(d.values()) == total
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/exam_paper_generation/test_generation_rules.py -q`
Expected: FAIL（`ModuleNotFoundError: contexts.exam_paper_generation.domain.anchor`）。

- [ ] **Step 3: 实现 anchor.py / count.py / allocation.py**

三个模块各含一个纯函数组，`slice_content_md` 用 `str.find` 返回切片或 `None`；`allocate_types` 严格按上述整除算法实现，保证 `sum == total` 且 `scenario >= 1`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/exam_paper_generation/test_generation_rules.py -q`
Expected: PASS（全部用例）。

- [ ] **Step 5: Commit**

```bash
git add contexts/exam_paper_generation/domain tests/contexts/exam_paper_generation
git commit -m "feat(exam-paper-generation): add deterministic anchor/count/allocation rules"
```

---

### Task 2: exam_grading — 确定性判分（选择题判分 + rubric 要点命中）

**Files:**
- Create: `contexts/exam_grading/domain/__init__.py`
- Create: `contexts/exam_grading/domain/grading.py`
- Test: `tests/contexts/exam_grading/test_grading.py`

**Interfaces:**
- Produces（纯函数，返回原始类型，不 import 其他 context）：
  - `grade_choice(answer_content: dict, reference_answer: dict) -> tuple[bool, float]`：`correct = answer_content.get("selected") == reference_answer.get("correct")`；返回 `(correct, 1.0 if correct else 0.0)`。
  - `rubric_hits(reference_answer: dict, answer_text: str) -> int`：`reference_answer` 中 `points` 字段（`list[str]`）逐条判断是否作为子串出现在 `answer_text`，返回命中条数。

- [ ] **Step 1: 写失败测试**

`tests/contexts/exam_grading/test_grading.py`：

```python
from contexts.exam_grading.domain.grading import grade_choice, rubric_hits

def test_grade_choice_correct():
    assert grade_choice({"selected": "B"}, {"correct": "B"}) == (True, 1.0)

def test_grade_choice_incorrect():
    assert grade_choice({"selected": "A"}, {"correct": "B"}) == (False, 0.0)

def test_grade_choice_missing_selected():
    assert grade_choice({}, {"correct": "B"}) == (False, 0.0)

def test_rubric_hits_counts_matching_points():
    ref = {"points": ["闭包", "作用域", "生命周期"]}
    assert rubric_hits(ref, "闭包和作用域是重点") == 2

def test_rubric_hits_zero():
    assert rubric_hits({"points": ["闭包"]}, "完全无关") == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/exam_grading/test_grading.py -q`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 实现 grading.py**

两个纯函数，`grade_choice` 用 `dict.get` 安全取值。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/exam_grading/test_grading.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add contexts/exam_grading/domain tests/contexts/exam_grading
git commit -m "feat(exam-grading): add deterministic choice grading and rubric matching"
```

---

### Task 3: self_practice — 领域层（端口协议 + DTO + 准入 + 合并）

**Files:**
- Create: `contexts/self_practice/domain/__init__.py`
- Create: `contexts/self_practice/domain/ports.py`
- Create: `contexts/self_practice/domain/admission.py`
- Create: `contexts/self_practice/domain/merge.py`
- Test: `tests/contexts/self_practice/test_domain.py`

**Interfaces:**
- Produces：
  - `ports.py`：
    ```python
    @dataclass
    class Question:
        question_id: str
        video_id: str
        question_type: str   # choice | short_answer | scenario | code
        content: dict
        reference_answer: dict
        explanation: str

    @dataclass
    class GradeResult:
        is_correct: bool
        score: float
        feedback: str

    class QuestionGenerationPort(Protocol):
        def plan_counts(self, video_ids: list[str]) -> dict[str, int]: ...
        def generate_by_video(self, video_id: str, count: int) -> list[Question]: ...

    class GradingPort(Protocol):
        def grade(self, question: Question, answer_content: dict) -> GradeResult: ...
    ```
  - `admission.py`：
    ```python
    @dataclass
    class AdmissionResult:
        level: str           # "block" | "soft" | "allow"
        total_seconds: int
        shortfall_seconds: int   # 0 when allowed

    def check_admission(total_seconds: int) -> AdmissionResult
    ```
    规则：`<1800 → block`、`1800–3599 → soft`、`>=3600 → allow`；`shortfall = max(0, 3600 - total_seconds)`。v1.0 中 `block` 与 `soft` 均拦截（软提示分级属 v1.1），但 `level` 字段保留三档供后续使用。
  - `merge.py`：
    ```python
    def merge_counts(counts: list[int], cap: int = 30, floor: int = 3) -> list[int]
    ```
    算法：`total = sum(counts)`；`total <= cap` 原样返回；否则 `scaled = [max(floor, c * cap // total) for c in counts]`；随后循环校正溢出——若 `sum(scaled) > cap`，反复将「最大且 > floor」的元素减 1，直到 `sum <= cap` 或无可减元素（保底与上限冲突时保底优先）。

- [ ] **Step 1: 写失败测试**

`tests/contexts/self_practice/test_domain.py`：

```python
from contexts.self_practice.domain.admission import check_admission
from contexts.self_practice.domain.merge import merge_counts
from contexts.self_practice.domain.ports import Question, GradeResult, QuestionGenerationPort, GradingPort

def test_check_admission_block():
    r = check_admission(1799)
    assert r.level == "block" and r.shortfall_seconds == 1801

def test_check_admission_soft():
    r = check_admission(1800)
    assert r.level == "soft" and r.shortfall_seconds == 1800

def test_check_admission_allow_boundary():
    r = check_admission(3600)
    assert r.level == "allow" and r.shortfall_seconds == 0

def test_check_admission_allow_over():
    assert check_admission(7200).level == "allow"

def test_check_admission_soft_upper_boundary():
    assert check_admission(3599).level == "soft"

def test_merge_counts_under_cap_unchanged():
    assert merge_counts([10, 10, 10]) == [10, 10, 10]

def test_merge_counts_scales_down():
    assert merge_counts([15, 15, 15]) == [10, 10, 10]
    assert merge_counts([20, 20]) == [15, 15]

def test_merge_counts_small_unchanged():
    assert merge_counts([5, 5]) == [5, 5]

def test_merge_counts_floor_beats_cap_when_too_many_videos():
    # 11 个视频 × 保底 3 = 33 > 上限 30：保底优先，不抛异常、无负题量
    result = merge_counts([3] * 11)
    assert all(c >= 3 for c in result)
    assert sum(result) >= 30

def test_question_and_grade_result_dataclasses():
    q = Question("q1", "v1", "choice", {"stem": "s"}, {"correct": "B"}, "exp")
    assert q.question_id == "q1" and q.video_id == "v1"
    g = GradeResult(True, 1.0, "正确")
    assert g.is_correct and g.score == 1.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/self_practice/test_domain.py -q`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 实现 ports.py / admission.py / merge.py**

`ports.py` 用 `dataclasses.dataclass` + `typing.Protocol`；`admission.py` 用 `AdmissionResult` 三档判定；`merge.py` 严格按上述算法。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/self_practice/test_domain.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add contexts/self_practice/domain tests/contexts/self_practice/test_domain.py
git commit -m "feat(self-practice): add ports, admission check, and merge counts"
```

---

### Task 4: 适配器（出题 + 批改 infrastructure 层，实现端口协议）

**Files:**
- Create: `contexts/exam_paper_generation/infrastructure/__init__.py`
- Create: `contexts/exam_paper_generation/infrastructure/adapter.py`
- Create: `contexts/exam_grading/infrastructure/__init__.py`
- Create: `contexts/exam_grading/infrastructure/adapter.py`
- Test: `tests/contexts/exam_paper_generation/test_adapter.py`、`tests/contexts/exam_grading/test_adapter.py`

**Interfaces:**
- Consumes: Task 1（anchor/count/allocation）、Task 2（grading）、Task 3（`Question`/`GradeResult`/`QuestionGenerationPort`/`GradingPort`）、`shared.infrastructure.llm.port.LLMPort`、`shared.infrastructure.db.models`。
- Produces：
  - `QuestionGenerationAdapter(session: Session, llm: LLMPort)`：
    - `plan_counts(self, video_ids: list[str]) -> dict[str, int]`：对每个 `video_id` 从 `Video` 表读 `duration_seconds`，`count_for_duration` 映射为 `{video_id: count}`。
    - `generate_by_video(self, video_id: str, count: int) -> list[Question]`：读 `VideoAnnotation`（start/end/fallback）与 `Chapter.content_md` → `slice_content_md` 截取（失败用 `fallback_range` 兜底：fallback 为 `None`/空时跳过该视频，返回空列表并记日志）→ `split_long_interval` 限长 → `has_code_block` → `allocate_types(count, has_code)` → 对每个 `(题型, n)` 调一次 LLM 生成 JSON 数组（n 道题），`json.loads` 解析；解析失败重试一次，仍失败则丢弃该题型并记日志，不影响其它题型。为每道题生成 `question_id = "q_" + uuid4().hex[:12]`，组装 `Question`。
  - `GradingAdapter(session: Session, llm: LLMPort)`：
    - `grade(self, question: Question, answer_content: dict) -> GradeResult`：`choice` → `grade_choice` 确定性判分，包装为 `GradeResult(is_correct, score, feedback="正确"/"错误")`；其它题型 → 构造含 `reference_answer` 与 rubric 要点的 prompt 调 LLM，期望返回 JSON `{"is_correct": bool, "score": float, "feedback": str}`；解析失败重试一次，仍失败则返回 `GradeResult(False, 0.0, "转人工批改")` 并记日志。

**LLM JSON 契约**（适配器与 LLM 的 prompt 中固定）：
- 选择题单题 JSON：`{"content": {"stem": str, "options": [str×4]}, "reference_answer": {"correct": str}, "explanation": str}`
- 简答题：`{"content": {"stem": str}, "reference_answer": {"points": [str×3~5]}, "explanation": str}`
- 场景分析题：`{"content": {"scenario": str, "task": str}, "reference_answer": {"points": [str]}, "explanation": str}`
- 代码题：`{"content": {"stem": str, "code": str}, "reference_answer": {"points": [str]}, "explanation": str}`

- [ ] **Step 1: 写失败测试**

`tests/contexts/exam_paper_generation/test_adapter.py`（用内存 SQLite + FakeLLM）：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa
from shared.infrastructure.db.models.sync_cache import Video, VideoAnnotation, Chapter
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.exam_paper_generation.infrastructure.adapter import QuestionGenerationAdapter

def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)

def test_plan_counts_reads_durations():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        Video(video_id="v2", chapter_id="c1", title="t", duration_seconds=1800),
    ])
    s.commit()
    a = QuestionGenerationAdapter(s, FakeLLMAdapter())
    assert a.plan_counts(["v1", "v2"]) == {"v1": 5, "v2": 10}

def test_generate_by_video_parses_llm_json():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"),
        Chapter(chapter_id="c1", title="ch", content_md="S 内容 E"),
    ])
    s.commit()
    llm = FakeLLMAdapter(responses=['[{"content": {"stem": "q", "options": ["A","B","C","D"]}, "reference_answer": {"correct": "A"}, "explanation": "x"}]'])
    a = QuestionGenerationAdapter(s, llm)
    qs = a.generate_by_video("v1", 1)
    assert len(qs) == 1 and qs[0].video_id == "v1" and qs[0].question_type == "choice"

def test_generate_by_video_bad_json_drops_and_continues():
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"),
        Chapter(chapter_id="c1", title="ch", content_md="S 内容 E"),
    ])
    s.commit()
    llm = FakeLLMAdapter(responses=["not json", "not json"])  # 重试一次仍失败
    a = QuestionGenerationAdapter(s, llm)
    qs = a.generate_by_video("v1", 3)  # 3 道题至少 3 个题型
    assert qs == []  # 该视频题目全部丢弃，但不抛异常

def test_generate_by_video_anchor_failure_returns_empty():
    # 坏锚点 + 无 fallbackRange：干净跳过（返回空列表），不抛异常
    s = _session()
    s.add_all([
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600),
        VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="不存在", end_sentence="也不存在"),
        Chapter(chapter_id="c1", title="ch", content_md="正常内容"),
    ])
    s.commit()
    a = QuestionGenerationAdapter(s, FakeLLMAdapter(responses=[]))
    assert a.generate_by_video("v1", 3) == []
```

`tests/contexts/exam_grading/test_adapter.py`：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.self_practice.domain.ports import Question
from contexts.exam_grading.infrastructure.adapter import GradingAdapter

def test_grade_choice_deterministic():
    s = Session(create_engine("sqlite:///:memory:"))
    a = GradingAdapter(s, FakeLLMAdapter())
    q = Question("q1", "v1", "choice", {"stem": "s", "options": ["A","B","C","D"]}, {"correct": "B"}, "exp")
    r = a.grade(q, {"selected": "B"})
    assert r.is_correct and r.score == 1.0

def test_grade_subjective_uses_llm():
    s = Session(create_engine("sqlite:///:memory:"))
    llm = FakeLLMAdapter(responses=['{"is_correct": true, "score": 0.8, "feedback": "要点基本命中"}'])
    a = GradingAdapter(s, llm)
    q = Question("q2", "v1", "short_answer", {"stem": "s"}, {"points": ["闭包"]}, "exp")
    r = a.grade(q, {"text": "闭包是..."})
    assert r.is_correct and r.score == 0.8

def test_grade_subjective_bad_json_falls_back_to_manual():
    s = Session(create_engine("sqlite:///:memory:"))
    a = GradingAdapter(s, FakeLLMAdapter(responses=["bad", "bad"]))
    q = Question("q3", "v1", "scenario", {"stem": "s"}, {"points": ["a"]}, "exp")
    r = a.grade(q, {"text": "x"})
    assert r.is_correct is False and r.feedback == "转人工批改"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/exam_paper_generation/test_adapter.py tests/contexts/exam_grading/test_adapter.py -q`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 实现两个 adapter**

`QuestionGenerationAdapter` 构造保存 `session`/`llm`；`generate_by_video` 按「截取 → 限长 → 题型分配 → 逐题型调 LLM → JSON 校验重试一次 → 组装 Question」实现；`plan_counts` 从 `Video` 表读时长。`GradingAdapter.grade` 按 `question_type` 分支，主观/代码走 LLM + rubric，失败兜底「转人工批改」。JSON 解析用 `shared.common.util.json_util.JsonUtil.loads` 或 `json.loads` 捕获异常。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/exam_paper_generation/test_adapter.py tests/contexts/exam_grading/test_adapter.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add contexts/exam_paper_generation/infrastructure contexts/exam_grading/infrastructure tests/contexts/exam_paper_generation/test_adapter.py tests/contexts/exam_grading/test_adapter.py
git commit -m "feat: add question generation and grading adapters implementing self_practice ports"
```

---

### Task 5: self_practice — 仓储 + 编排服务（application/infrastructure 层）

**Files:**
- Create: `contexts/self_practice/infrastructure/__init__.py`
- Create: `contexts/self_practice/infrastructure/repository.py`
- Create: `contexts/self_practice/application/__init__.py`
- Create: `contexts/self_practice/application/service.py`
- Test: `tests/contexts/self_practice/test_service.py`

**Interfaces:**
- Consumes: Task 3（ports/admission/merge）、`shared.infrastructure.db.models`、`shared.common.exception.base.BadRequestError`。
- Produces：
  - `PracticeRepository(session: Session)`：
    - `list_completed_videos(student_id: str, chapter_id: str) -> list[dict]`：join `StudentVideoProgress`（`completed_at` 非空）与 `Video`（`chapter_id` 匹配），返回 `[{"videoId", "title", "durationSeconds"}]`。
    - `find_questions_by_video(video_id: str) -> list[Question]`：查 `PracticeQuestion` 中 `video_id` 相等且 `status == "active"`，组装 `Question`。
    - `save_session(practice_id: str, student_id: str, video_ids: list[str]) -> None`
    - `save_questions(practice_id: str, questions: list[Question]) -> None`（批量插入 `PracticeQuestion`，`status="active"`）
    - `save_answers(practice_id: str, student_id: str, answers: list[tuple[Question, dict, GradeResult]]) -> None`（批量插入 `PracticeAnswer`，`practice_id` 记当前练习）
    - `get_question(question_id: str) -> Question | None`：按主键查 `PracticeQuestion`，组装 `Question`。
    - `get_practice_result(practice_id: str) -> dict | None`：查 `PracticeSession` + 该 `practice_id` 的 `PracticeAnswer`（join `PracticeQuestion` 取参考答案/解析），组装 `{"practiceId", "summary", "results"}`；不存在返回 `None`。
  - `PracticeService(qgen: QuestionGenerationPort, grader: GradingPort, repo: PracticeRepository)`：
    - `available_videos(student_id: str, chapter_id: str) -> list[dict]`
    - `start_practice(student_id: str, chapter_id: str, video_ids: list[str]) -> dict`：准入校验（累加选中视频时长，`check_admission`；`level != "allow"` 抛 `BadRequestError(f"累计时长不足 60 分钟，还差 {shortfall//60} 分钟")`）→ 生成 `practice_id = "pr_" + uuid4().hex[:12]` → 分区复用/新建 → 新建视频 `qgen.plan_counts` → `merge_counts` → 逐视频 `qgen.generate_by_video`，复用视频 `repo.find_questions_by_video` 后 `random.shuffle` 打乱 → 合并 → `repo.save_session` + `repo.save_questions` → 返回 `{"practiceId", "groupedByVideo": True, "questions": [去参考答案/解析的题]}`。
    - `submit_practice(practice_id: str, answers: list[dict]) -> dict`：对每个 `answers` 元素按 `questionId` 用 `repo.get_question` 取题（缺失则跳过并记日志）→ `grader.grade` → 批量 `repo.save_answers` → 返回 `{"practiceId", "summary": {"total", "correct", "score"}, "results": [{"questionId", "isCorrect", "score", "referenceAnswer", "explanation", "feedback"}]}`。
    - `get_practice(practice_id: str) -> dict | None`：委托 `repo.get_practice_result`。

**说明（v1.0 简化，写入 ledger 记录）**：FR-016 的「总题量上限 30」仅作用于**新建题目**的合并；复用题目按既有数量原样返回，不参与缩减（复用与上限的交互属 v1.1「总题量上限优化」）。

- [ ] **Step 1: 写失败测试**

`tests/contexts/self_practice/test_service.py`（用 fake ports 隔离编排逻辑，配内存 SQLite 仓储）：

```python
import random
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa
from shared.infrastructure.db.models.sync_cache import Video, StudentVideoProgress
from shared.common.exception.base import BadRequestError
from contexts.self_practice.domain.ports import Question, GradeResult
from contexts.self_practice.infrastructure.repository import PracticeRepository
from contexts.self_practice.application.service import PracticeService

class FakeQGen:
    def __init__(self): self.calls = 0
    def plan_counts(self, video_ids):
        return {vid: 10 for vid in video_ids}
    def generate_by_video(self, video_id, count):
        self.calls += 1
        return [Question(f"q_{video_id}_{i}", video_id, "choice",
                         {"stem": "s", "options": ["A","B","C","D"]},
                         {"correct": "A"}, "exp") for i in range(count)]

class FakeGrader:
    def grade(self, question, answer_content):
        return GradeResult(True, 1.0, "正确")

def _service(videos=None, completed=None):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    if videos:
        s.add_all(videos); s.commit()
    if completed:
        s.add_all(completed); s.commit()
    return PracticeService(FakeQGen(), FakeGrader(), PracticeRepository(s))

def test_start_admission_blocked():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600)])
    with pytest.raises(BadRequestError):
        svc.start_practice("stu", "c1", ["v1"])

def test_start_generates_and_persists():
    svc = _service(videos=[
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600),
    ])
    result = svc.start_practice("stu", "c1", ["v1"])
    assert result["practiceId"].startswith("pr_")
    assert result["groupedByVideo"] is True
    assert len(result["questions"]) == 10

def test_start_reuses_without_regenerating():
    qgen = FakeQGen()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)); s.commit()
    repo = PracticeRepository(s)
    # 预置已有题目（复用）
    repo.save_questions("pr_old", [Question("q_existing", "v1", "choice",
        {"stem": "s", "options": ["A","B","C","D"]}, {"correct": "A"}, "exp")])
    svc = PracticeService(qgen, FakeGrader(), repo)
    result = svc.start_practice("stu", "c1", ["v1"])
    assert qgen.calls == 0  # 未调用生成
    assert [q["questionId"] for q in result["questions"]] == ["q_existing"]

def test_available_videos_only_completed():
    svc = _service(
        videos=[Video(video_id="v1", chapter_id="c1", title="t1", duration_seconds=600),
                Video(video_id="v2", chapter_id="c1", title="t2", duration_seconds=600)],
        completed=[StudentVideoProgress(student_id="stu", video_id="v1", chapter_id="c1",
                                        completed_at=datetime(2026, 11, 17))],
    )
    vids = svc.available_videos("stu", "c1")
    assert [v["videoId"] for v in vids] == ["v1"]

def test_submit_grades_and_returns_summary():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    start = svc.start_practice("stu", "c1", ["v1"])
    pid = start["practiceId"]
    answers = [{"questionId": q["questionId"], "answerContent": {"selected": "A"}}
               for q in start["questions"]]
    result = svc.submit_practice(pid, answers)
    assert result["summary"]["total"] == 10
    assert result["summary"]["correct"] == 10
    assert len(result["results"]) == 10
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/self_practice/test_service.py -q`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 实现 repository.py 与 service.py**

`repository.py` 用 SQLAlchemy `Session` 做查询与批量插入；`service.py` 编排准入/复用/合并/生成/判分，`random.shuffle` 打乱复用题目，`submit_practice` 累加 `summary`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/self_practice/test_service.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add contexts/self_practice/infrastructure contexts/self_practice/application tests/contexts/self_practice/test_service.py
git commit -m "feat(self-practice): add repository and orchestration service"
```

---

### Task 6: API 路由 + Pydantic schema + 组合根装配

**Files:**
- Create: `api/schemas/practice.py`
- Create: `api/routes/practice.py`
- Create: `api/dependencies.py`
- Modify: `api/main.py`（include practice router）
- Test: `tests/test_practice_api.py`

**Interfaces:**
- Consumes: Task 5（`PracticeService`/`PracticeRepository`）、Task 4（两个 adapter）、`shared.infrastructure.db.session.get_session`、`shared.infrastructure.llm.factory.get_llm`、`shared.infrastructure.config.get_settings`、`api.schemas.ok`。
- Produces（对外 API，统一响应包裹在 `data` 中）：
  - `GET /api/v1/practice/available-videos?studentId=&chapterId=` → `data = {"videos": [{"videoId","title","durationSeconds"}]}`
  - `POST /api/v1/practice/start` body `{"studentId","chapterId","videoIds":[...]}` → `data = {"practiceId","groupedByVideo":true,"questions":[{"questionId","videoId","questionType","content"}]}`（不含参考答案/解析）
  - `POST /api/v1/practice/submit` body `{"practiceId","answers":[{"questionId","answerContent":{}}]}` → `data = {"practiceId","summary":{"total","correct","score"},"results":[{"questionId","isCorrect","score","referenceAnswer","explanation","feedback"}]}`
  - `GET /api/v1/practice/{practiceId}` → 同 submit 结果结构
  - `api/dependencies.py`：`get_practice_service(session=Depends(get_session)) -> PracticeService`，内部 `get_llm(get_settings())` 装配 `QuestionGenerationAdapter(session, llm)`、`GradingAdapter(session, llm)`、`PracticeRepository(session)`，返回 `PracticeService`。

- [ ] **Step 1: 写失败测试**

`tests/test_practice_api.py`（TestClient + 内存 SQLite 依赖覆盖 + FakeLLM）：

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa
from shared.infrastructure.db.models.sync_cache import Video
from api.main import create_app
from api.dependencies import get_practice_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.exam_paper_generation.infrastructure.adapter import QuestionGenerationAdapter
from contexts.exam_grading.infrastructure.adapter import GradingAdapter
from contexts.self_practice.infrastructure.repository import PracticeRepository
from contexts.self_practice.application.service import PracticeService

def _client(seed=None):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    if seed:
        seed(s)
        s.commit()
    def override_session():
        yield s
    def override_service():
        llm = FakeLLMAdapter()
        return PracticeService(
            QuestionGenerationAdapter(s, llm), GradingAdapter(s, llm), PracticeRepository(s))
    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_practice_service] = override_service
    return TestClient(app)

def test_available_videos_endpoint():
    c = _client()
    r = c.get("/api/v1/practice/available-videos?studentId=stu&chapterId=c1")
    assert r.status_code == 200
    assert r.json()["code"] == 0

def test_start_endpoint_admission_blocked():
    c = _client()
    r = c.post("/api/v1/practice/start", json={"studentId": "stu", "chapterId": "c1", "videoIds": []})
    assert r.status_code == 400  # 空视频累计时长 0 < 60 分钟

def test_start_and_submit_roundtrip():
    def seed(s):
        s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600))
    c = _client(seed=seed)
    start = c.post("/api/v1/practice/start",
                   json={"studentId": "stu", "chapterId": "c1", "videoIds": ["v1"]})
    assert start.status_code == 200
    data = start.json()["data"]
    pid = data["practiceId"]
    assert pid.startswith("pr_") and data["groupedByVideo"] is True
    answers = [{"questionId": q["questionId"], "answerContent": {"selected": "A"}}
               for q in data["questions"]]
    sub = c.post("/api/v1/practice/submit", json={"practiceId": pid, "answers": answers})
    assert sub.status_code == 200
    body = sub.json()["data"]
    assert body["summary"]["total"] == len(data["questions"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_practice_api.py -q`
Expected: FAIL（`ModuleNotFoundError: api.routes.practice`）。

- [ ] **Step 3: 实现 schemas / routes / dependencies / main 装配**

`api/schemas/practice.py` 定义 Pydantic 请求/响应模型；`api/routes/practice.py` 四个路由，handler 为 `async def`，读 `get_trace_id()` 回填 `traceId`；`api/dependencies.py` 提供 `get_practice_service`；`api/main.py` 的 `create_app` 中 `app.include_router(practice_router)`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_practice_api.py -q`
Expected: PASS。

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通过（阶段 0 的 32 项 + 阶段 1 新增全绿）。

- [ ] **Step 6: Commit**

```bash
git add api tests/test_practice_api.py
git commit -m "feat(api): add practice endpoints and compose adapters in dependencies"
```

---

### Task 7: 依赖规则检查（import-linter 合约更新）

**Files:**
- Modify: `.importlinter`
- Test: 运行 `lint-imports` 作为验证

**Interfaces:**
- Consumes: Task 1–6 全部包。

**变更**：将 `contexts-independent`（7 上下文全独立）替换为两条合约，表达真实的编排依赖倒置（生产方 `exam_paper_generation`/`exam_grading` 仅允许 import `self_practice` 的端口抽象，其余一律禁止）：

```ini
[importlinter:contract:contexts-leaf-independent]
name = Leaf contexts and self_practice stay independent
type = independence
modules =
    contexts.sales_assistant
    contexts.teaching_assistant
    contexts.course_assistant
    contexts.learning_analytics
    contexts.self_practice

[importlinter:contract:practice-producers-one-way]
name = Practice producers may only depend on self_practice ports
type = forbidden
source_modules =
    contexts.exam_paper_generation
    contexts.exam_grading
forbidden_modules =
    contexts.exam_paper_generation
    contexts.exam_grading
    contexts.sales_assistant
    contexts.teaching_assistant
    contexts.course_assistant
    contexts.learning_analytics
```

- [ ] **Step 1: 修改 `.importlinter`**

保留 `shared-layers`、`shared-isolated` 不变，替换 `contexts-independent` 为上述两条。

- [ ] **Step 2: 运行检查**

Run: `.venv/Scripts/python.exe -m importlinter.cli lint-imports`（或 `lint-imports`）
Expected: 通过（`Kept contracts: ...` 无 `Broken contracts`，退出码 0）。若报违规，逐条修正 import 直至通过。

- [ ] **Step 3: Commit**

```bash
git add .importlinter
git commit -m "chore: express practice one-way dependency in import-linter contracts"
```

---

## 完成标准（阶段 1 验收）

- `.venv/Scripts/python.exe -m pytest -q` 全绿（阶段 0 + 阶段 1 全部单测/接口测试）。
- `lint-imports` 通过（shared-layers、shared-isolated、contexts-leaf-independent、practice-producers-one-way 全部 kept）。
- 确定性逻辑单测覆盖：锚点截取、超长二次切分、代码块检测、题量映射、题型分配（含边界 `sum==total`）、准入三档边界、多视频合并。
- 4 个 practice API 可用：available-videos / start / submit / get；选择题自动判分、主观题 FakeLLM 批改、准入拦截、题目复用不重复生成。
- 数据持久化：start 写 `practice_session` + `practice_question`，submit 写 `practice_answer`（内存 SQLite 验证）。
- git 历史含每个 Task 一次 commit。

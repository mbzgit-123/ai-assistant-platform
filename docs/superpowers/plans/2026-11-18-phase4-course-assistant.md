# 阶段 4 — 课程 Agent + 督学 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `contexts/course_assistant/` 内交付 FR-006 学习路径规划、FR-007 学习计划落地与动态重规划、FR-009 智能督学。

**Architecture:** 沿用阶段 0–3 的端口 + 轻量适配器模式。路径顺序由「岗位→课程路径知识库」确定性给出，LLM 只生成每步「学习内容」文案（失败兜底）；学习计划无状态按需重算（读取真实进度剔除已完成课程）；督学通过 `MessageChannelPort` 存根适配器 + 显式幂等端点触发。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy 2.x、Pydantic v2、structlog、pytest、FakeLLMAdapter。

**Spec:**
- `docs/superpowers/specs/2026-11-18-phase4-course-assistant-design.md`（本计划据其展开）
- `docs/码帮智 · 教育智能体平台需求规格说明书.md` FR-006/007/009

## Global Constraints

- DDD 依赖规则：`contexts/course_assistant` 只依赖 `shared` + 自身；接口层在 `contexts/course_assistant/interface/`，不进顶层 `api/`。
- 学习计划的「顺序」必须确定性（知识库 + 前置依赖），LLM 只生成「学习内容」文案，失败时兜底。
- 「有基础」判定规则（规格未给谓词，本计划拍板）：`Student.major` 非空即视为有基础 → 跳过 `is_foundation=True` 的前置步骤；否则零基础保留全部。
- 端口 + 内存/存根适配器：不接真实短信/微信、不建新 DB 表。
- 统一响应信封 `ok(data=..., trace_id=get_trace_id())`；LLM 端口 `chat(messages) -> LLMResult(content)`（纯文本，无 JSON 模式）。
- 测试文件命名必须带 `course_` 前缀（`test_course_repository.py`、`test_course_service.py`），避免与既有 `test_repository.py`/`test_service.py` 在 pytest rootdir 收集时发生 import file mismatch。
- 测试命令：`.venv/Scripts/python.exe -m pytest`（仓库根目录）。

## Review Focus

规格未明说、但真人使用时最可能踩坑的输入（每条都有对应任务的测试钉住）：

1. **未知岗位方向**（`position` 不在 `POSITIONS`）→ 应返回明确错误（400）而非静默返回空计划。→ Task 4 `test_generate_plan_unknown_position_raises`。
2. **学员只有学历无专业**（`education` 有、`major` 空）→ 判定为零基础，保留前置步骤。→ Task 4 `test_generate_plan_keeps_foundation_for_zero_basis`。
3. **学员从未完课**（`last_completed_at=None`）→ 督学触发升级提醒，不抛异常。→ Task 6 `test_never_completed_triggers_escalation`。
4. **重规划时课程已全部完成** → 返回空 items，不报错。→ Task 5 `test_replan_all_completed_returns_empty`。
5. **LLM 返回空内容** → 学习内容兜底为 `学习《<标题>》`，不返回空串。→ Task 4 `test_generate_plan_fallback_content_when_llm_empty`。

---

### Task 1: 岗位常量与计划领域对象

**Files:**
- Create: `contexts/course_assistant/domain/__init__.py`
- Create: `contexts/course_assistant/domain/positions.py`
- Create: `contexts/course_assistant/domain/path.py`
- Test: `tests/contexts/course_assistant/test_positions.py`
- Test: `tests/contexts/course_assistant/test_path.py`

**Interfaces:**
- Produces: `POSITIONS: tuple[str, ...]`；`PathStep(course_id, chapter_ids, is_foundation=False)`；`PlanItem(course_id, chapter_ids, title, content)`；`LearningPlan(position, student_id, items)` 带 `.to_dict() -> dict`。

- [ ] **Step 1: 写失败测试**

`tests/contexts/course_assistant/test_positions.py`：
```python
from contexts.course_assistant.domain.positions import POSITIONS


def test_positions_contain_three_job_roles():
    assert POSITIONS == ("Java 开发岗", "大模型算法岗", "大模型应用开发岗")
```

`tests/contexts/course_assistant/test_path.py`：
```python
from contexts.course_assistant.domain.path import LearningPlan, PathStep, PlanItem


def test_path_step_default_not_foundation():
    s = PathStep(course_id="c1", chapter_ids=["ch1"])
    assert s.is_foundation is False


def test_learning_plan_to_dict_serializes_items():
    plan = LearningPlan(
        position="大模型应用开发岗",
        student_id="s1",
        items=[PlanItem(course_id="c1", chapter_ids=["ch1"], title="Python 基础", content="学习 Python")],
    )
    assert plan.to_dict() == {
        "position": "大模型应用开发岗",
        "studentId": "s1",
        "items": [
            {"courseId": "c1", "chapterIds": ["ch1"], "title": "Python 基础", "content": "学习 Python"}
        ],
    }
```

- [ ] **Step 2: 运行验证失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_positions.py tests/contexts/course_assistant/test_path.py -v`
Expected: FAIL（`ModuleNotFoundError: contexts.course_assistant.domain.positions` / `.path`）

- [ ] **Step 3: 实现 `POSITIONS`、`PathStep`、`PlanItem`、`LearningPlan`**

`positions.py`：`POSITIONS = ("Java 开发岗", "大模型算法岗", "大模型应用开发岗")`。
`path.py`：三个 `@dataclass`（字段见 Interfaces）；`LearningPlan.to_dict()` 返回 `{"position", "studentId", "items": [{"courseId","chapterIds","title","content"}]}`。

- [ ] **Step 4: 运行验证通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_positions.py tests/contexts/course_assistant/test_path.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/course_assistant/domain/__init__.py contexts/course_assistant/domain/positions.py contexts/course_assistant/domain/path.py tests/contexts/course_assistant/test_positions.py tests/contexts/course_assistant/test_path.py
git commit -m "feat(course-assistant): add position constants and plan domain objects"
```

---

### Task 2: 路径知识库端口 + 内存实现

**Files:**
- Create: `contexts/course_assistant/domain/ports.py`（本任务只加 `PathKnowledgePort`）
- Create: `contexts/course_assistant/infrastructure/__init__.py`
- Create: `contexts/course_assistant/infrastructure/path_knowledge.py`
- Test: `tests/contexts/course_assistant/test_path_knowledge.py`

**Interfaces:**
- Consumes: `PathStep`（Task 1）。
- Produces: `PathKnowledgePort.get_path(position: str) -> list[PathStep]`；`InMemoryPathKnowledge(paths: dict[str, list[PathStep]] | None = None)`，`DEFAULT_PATHS: dict[str, list[PathStep]]`。

- [ ] **Step 1: 写失败测试**

`tests/contexts/course_assistant/test_path_knowledge.py`：
```python
from contexts.course_assistant.infrastructure.path_knowledge import DEFAULT_PATHS, InMemoryPathKnowledge
from contexts.course_assistant.domain.path import PathStep


def test_default_path_orders_steps_with_foundation_first():
    kb = InMemoryPathKnowledge()
    steps = kb.get_path("大模型应用开发岗")
    assert [s.course_id for s in steps] == ["ai_py_basic", "llm_foundation", "llm_app_dev"]
    assert steps[0].is_foundation is True
    assert steps[1].is_foundation is False


def test_unknown_position_returns_empty():
    kb = InMemoryPathKnowledge()
    assert kb.get_path("不存在的岗位") == []


def test_custom_paths_override_defaults():
    kb = InMemoryPathKnowledge({"测试岗": [PathStep("c1", ["ch1"], is_foundation=True)]})
    assert kb.get_path("测试岗")[0].course_id == "c1"


def test_all_three_positions_have_paths():
    kb = InMemoryPathKnowledge()
    for p in ("Java 开发岗", "大模型算法岗", "大模型应用开发岗"):
        assert kb.get_path(p) != []
```

- [ ] **Step 2: 运行验证失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_path_knowledge.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `PathKnowledgePort` + `InMemoryPathKnowledge` + `DEFAULT_PATHS`**

`ports.py` 定义 `class PathKnowledgePort(Protocol): def get_path(self, position: str) -> list[PathStep]: ...`。
`path_knowledge.py`：`DEFAULT_PATHS` 三个岗位各有 3–4 个 `PathStep`，每个岗位第一个步骤 `is_foundation=True`（基础课），后续为 `False`；`get_path` 返回 `list(self._paths.get(position, []))`。每个 `PathStep` 的 `course_id`/`chapter_ids` 用稳定字符串（如 `"ai_py_basic"`/`["ai_py_basic_c1"]`）。

- [ ] **Step 4: 运行验证通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_path_knowledge.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/course_assistant/domain/ports.py contexts/course_assistant/infrastructure/__init__.py contexts/course_assistant/infrastructure/path_knowledge.py tests/contexts/course_assistant/test_path_knowledge.py
git commit -m "feat(course-assistant): add in-memory position-course path knowledge"
```

---

### Task 3: 学习数据访问端口 + 仓储

**Files:**
- Modify: `contexts/course_assistant/domain/ports.py`（加 `StudentProfile`、`ProgressPort`）
- Create: `contexts/course_assistant/infrastructure/repository.py`
- Test: `tests/contexts/course_assistant/test_course_repository.py`

**Interfaces:**
- Consumes: `StudentProfile`（本任务定义）。
- Produces: `StudentProfile(education: str | None, major: str | None)`；`ProgressPort` 五方法：
  - `get_profile(student_id: str) -> StudentProfile | None`
  - `completed_course_ids(student_id: str) -> set[str]`
  - `enrolled_student_ids() -> list[str]`
  - `last_completed_at(student_id: str) -> datetime | None`
  - `get_course_title(course_id: str) -> str | None`
  - `CourseRepository(session: Session)` 实现上述端口。

- [ ] **Step 1: 写失败测试**

`tests/contexts/course_assistant/test_course_repository.py`（关键断言，夹具用内存 SQLite StaticPool）：
```python
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import (
    Chapter, Course, Student, StudentCourse, StudentVideoProgress,
)
from contexts.course_assistant.infrastructure.repository import CourseRepository


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_get_profile_returns_education_and_major():
    s = _session()
    s.add(Student(student_id="s1", education="本科", major="计算机"))
    s.commit()
    p = CourseRepository(s).get_profile("s1")
    assert p.education == "本科"
    assert p.major == "计算机"


def test_get_profile_missing_returns_none():
    assert CourseRepository(_session()).get_profile("nope") is None


def test_completed_course_ids_joins_via_chapter():
    s = _session()
    s.add_all([
        Chapter(chapter_id="ch1", course_id="course_a"),
        Chapter(chapter_id="ch2", course_id="course_b"),
        StudentVideoProgress(student_id="s1", chapter_id="ch1", completed_at=datetime.utcnow()),
        StudentVideoProgress(student_id="s1", chapter_id="ch2", completed_at=None),
    ])
    s.commit()
    assert CourseRepository(s).completed_course_ids("s1") == {"course_a"}


def test_enrolled_student_ids_distinct():
    s = _session()
    s.add_all([StudentCourse(student_id="s1", course_id="c1"), StudentCourse(student_id="s2", course_id="c2")])
    s.commit()
    assert CourseRepository(s).enrolled_student_ids() == ["s1", "s2"]


def test_last_completed_at_returns_latest():
    s = _session()
    now = datetime.utcnow()
    later = now - timedelta(days=1)
    s.add_all([
        StudentVideoProgress(student_id="s1", chapter_id="ch1", completed_at=now - timedelta(days=5)),
        StudentVideoProgress(student_id="s1", chapter_id="ch2", completed_at=later),
    ])
    s.commit()
    last = CourseRepository(s).last_completed_at("s1")
    assert last is not None
    assert abs((last - later).total_seconds()) < 1


def test_get_course_title():
    s = _session()
    s.add(Course(course_id="c1", name="Python 基础"))
    s.commit()
    assert CourseRepository(s).get_course_title("c1") == "Python 基础"
```

- [ ] **Step 2: 运行验证失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_course_repository.py -v`
Expected: FAIL（`ModuleNotFoundError` / `ImportError`）

- [ ] **Step 3: 实现 `StudentProfile`、`ProgressPort`、`CourseRepository`**

`completed_course_ids` 用 join：`select(Chapter.course_id).join(StudentVideoProgress, StudentVideoProgress.chapter_id == Chapter.chapter_id).where(student_id==, completed_at.isnot(None)).distinct()`，过滤 `None` 后返回 set。`last_completed_at` 用 `select(func.max(StudentVideoProgress.completed_at))`。`get_course_title` 用 `session.get(Course, course_id)`。

- [ ] **Step 4: 运行验证通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_course_repository.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/course_assistant/domain/ports.py contexts/course_assistant/infrastructure/repository.py tests/contexts/course_assistant/test_course_repository.py
git commit -m "feat(course-assistant): add learning progress repository"
```

---

### Task 4: 课程 Agent 服务 — 学习计划生成

**Files:**
- Create: `contexts/course_assistant/application/__init__.py`
- Create: `contexts/course_assistant/application/service.py`
- Test: `tests/contexts/course_assistant/test_course_service.py`

**Interfaces:**
- Consumes: `PathStep`、`PathKnowledgePort`、`ProgressPort`、`LLMPort`（Task 1–3）。
- Produces: `CourseAssistantService(llm, path_knowledge, progress)`；`generate_plan(position: str, student_id: str | None) -> LearningPlan`。

- [ ] **Step 1: 写失败测试**

`tests/contexts/course_assistant/test_course_service.py`（用 `InMemoryPathKnowledge` + `FakeLLMAdapter` + 手写 `_StubProgress`）：
```python
import pytest

from shared.common.exception.base import BadRequestError
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.course_assistant.application.service import CourseAssistantService
from contexts.course_assistant.domain.path import PathStep
from contexts.course_assistant.domain.ports import StudentProfile
from contexts.course_assistant.infrastructure.path_knowledge import InMemoryPathKnowledge


class _StubProgress:
    def __init__(self, profile=None, titles=None):
        self.profile = profile
        self.titles = titles or {}

    def get_profile(self, student_id):
        return self.profile

    def get_course_title(self, course_id):
        return self.titles.get(course_id)


def _svc(llm_responses=None, progress=None):
    kb = InMemoryPathKnowledge({
        "大模型应用开发岗": [
            PathStep("found", ["ch0"], is_foundation=True),
            PathStep("adv1", ["ch1"], is_foundation=False),
        ],
    })
    llm = FakeLLMAdapter(responses=llm_responses if llm_responses is not None else ["学习内容"])
    return CourseAssistantService(llm, kb, progress or _StubProgress())


def test_generate_plan_keeps_foundation_for_zero_basis():
    svc = _svc(progress=_StubProgress(profile=StudentProfile(education="本科", major=None)))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert [i.course_id for i in plan.items] == ["found", "adv1"]


def test_generate_plan_skips_foundation_for_experienced():
    svc = _svc(progress=_StubProgress(profile=StudentProfile(education="本科", major="计算机")))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert [i.course_id for i in plan.items] == ["adv1"]


def test_generate_plan_uses_title_and_llm_content():
    titles = {"found": "Python 基础", "adv1": "大模型应用"}
    svc = _svc(llm_responses=["学习 Python 基础语法"], progress=_StubProgress(titles=titles))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert plan.items[0].title == "Python 基础"
    assert plan.items[0].content == "学习 Python 基础语法"


def test_generate_plan_fallback_content_when_llm_empty():
    titles = {"found": "Python 基础", "adv1": "大模型应用"}
    svc = _svc(llm_responses=[""], progress=_StubProgress(titles=titles))
    plan = svc.generate_plan("大模型应用开发岗", "s1")
    assert plan.items[0].content == "学习《Python 基础》"


def test_generate_plan_unknown_position_raises():
    svc = _svc()
    with pytest.raises(BadRequestError):
        svc.generate_plan("不存在的岗位", "s1")
```

- [ ] **Step 2: 运行验证失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_course_service.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `CourseAssistantService.generate_plan`**

流程：`steps = path_knowledge.get_path(position)`；空则 `raise BadRequestError(f"未知岗位方向: {position}")`；`student_id` 非空且 `progress.get_profile(student_id).major` 非空 → 过滤掉 `is_foundation` 步骤；对每个 `PathStep` 生成 `PlanItem`（`title = get_course_title(course_id) or course_id`，`content = llm.chat([...]).content.strip() or f"学习《{title}》"`）。返回 `LearningPlan(position, student_id, items)`。

- [ ] **Step 4: 运行验证通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_course_service.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/course_assistant/application/__init__.py contexts/course_assistant/application/service.py tests/contexts/course_assistant/test_course_service.py
git commit -m "feat(course-assistant): generate personalized learning plan"
```

---

### Task 5: 课程 Agent 服务 — 动态重规划

**Files:**
- Modify: `contexts/course_assistant/application/service.py`（加 `replan`）
- Test: `tests/contexts/course_assistant/test_course_service.py`（追加）

**Interfaces:**
- Consumes: `generate_plan`（Task 4）、`ProgressPort.completed_course_ids`（Task 3）。
- Produces: `CourseAssistantService.replan(position: str, student_id: str) -> LearningPlan`。

- [ ] **Step 1: 写失败测试**（追加到 `test_course_service.py`，`_StubProgress` 增加 `completed` 字段与 `completed_course_ids` 方法）

```python
class _StubProgress:
    def __init__(self, profile=None, titles=None, completed=None):
        self.profile = profile
        self.titles = titles or {}
        self.completed = completed or set()

    def get_profile(self, student_id):
        return self.profile

    def get_course_title(self, course_id):
        return self.titles.get(course_id)

    def completed_course_ids(self, student_id):
        return self.completed


def test_replan_removes_completed_courses():
    svc = _svc(progress=_StubProgress(completed={"adv1"}, titles={"found": "基础", "adv1": "进阶"}))
    plan = svc.replan("大模型应用开发岗", "s1")
    assert [i.course_id for i in plan.items] == ["found"]


def test_replan_all_completed_returns_empty():
    svc = _svc(progress=_StubProgress(completed={"found", "adv1"}, titles={"found": "基础", "adv1": "进阶"}))
    plan = svc.replan("大模型应用开发岗", "s1")
    assert plan.items == []
```

- [ ] **Step 2: 运行验证失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_course_service.py -v`
Expected: FAIL（`AttributeError: 'CourseAssistantService' object has no attribute 'replan'`）

- [ ] **Step 3: 实现 `replan`**

`plan = self.generate_plan(position, student_id)`；`done = self._progress.completed_course_ids(student_id)`；`plan.items = [i for i in plan.items if i.course_id not in done]`；返回 `plan`。

- [ ] **Step 4: 运行验证通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_course_service.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/course_assistant/application/service.py tests/contexts/course_assistant/test_course_service.py
git commit -m "feat(course-assistant): re-plan based on learning progress"
```

---

### Task 6: 督学服务 + 消息通道

**Files:**
- Create: `contexts/course_assistant/domain/supervision.py`
- Modify: `contexts/course_assistant/domain/ports.py`（加 `MessageChannelPort`）
- Create: `contexts/course_assistant/infrastructure/message_channel.py`
- Modify: `contexts/course_assistant/application/service.py`（加 `SupervisionService`）
- Test: `tests/contexts/course_assistant/test_message_channel.py`
- Test: `tests/contexts/course_assistant/test_supervision.py`

**Interfaces:**
- Consumes: `ProgressPort.enrolled_student_ids`/`last_completed_at`（Task 3）。
- Produces:
  - `MessageChannelPort.send(student_id: str, content: str) -> str`
  - `StubMessageChannel()` 带 `.sent: list[dict]`（`{"messageId","studentId","content"}`）
  - `supervision.py` 常量：`IDLE_REMINDER_DAYS = 3`、`ESCALATION_DAYS = 7`、`IDLE_REMINDER_MESSAGE`、`ESCALATION_MESSAGE`
  - `SupervisionService(progress, message_channel).check_and_notify(now: datetime | None = None) -> list[dict]`（每项 `{"studentId","messageId","content","level"}`，`level ∈ {"reminder","escalation"}`）

- [ ] **Step 1: 写失败测试**

`tests/contexts/course_assistant/test_message_channel.py`：
```python
from contexts.course_assistant.infrastructure.message_channel import StubMessageChannel


def test_send_returns_message_id_and_records():
    ch = StubMessageChannel()
    msg_id = ch.send("s1", "提醒学习")
    assert msg_id.startswith("msg_")
    assert ch.sent == [{"messageId": msg_id, "studentId": "s1", "content": "提醒学习"}]
```

`tests/contexts/course_assistant/test_supervision.py`：
```python
from datetime import datetime, timedelta

from contexts.course_assistant.application.service import SupervisionService
from contexts.course_assistant.domain.supervision import ESCALATION_MESSAGE, IDLE_REMINDER_MESSAGE


class _StubProgress:
    def __init__(self, enrolled, last_completed=None):
        self.enrolled = enrolled
        self.last_completed = last_completed or {}

    def enrolled_student_ids(self):
        return self.enrolled

    def last_completed_at(self, student_id):
        return self.last_completed.get(student_id)


class _StubChannel:
    def __init__(self):
        self.sent = []

    def send(self, student_id, content):
        self.sent.append((student_id, content))
        return f"msg_{student_id}"


def _svc(enrolled, last):
    return SupervisionService(_StubProgress(enrolled, last), _StubChannel())


def test_never_completed_triggers_escalation():
    svc = _svc(["s1"], {})
    sent = svc.check_and_notify(now=datetime(2026, 11, 18, 12, 0, 0))
    assert len(sent) == 1
    assert sent[0]["content"] == ESCALATION_MESSAGE
    assert sent[0]["level"] == "escalation"
    assert sent[0]["messageId"] == "msg_s1"


def test_idle_3_days_triggers_reminder():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1"], {"s1": now - timedelta(days=3)})
    sent = svc.check_and_notify(now=now)
    assert sent[0]["level"] == "reminder"
    assert sent[0]["content"] == IDLE_REMINDER_MESSAGE


def test_idle_7_days_triggers_escalation():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1"], {"s1": now - timedelta(days=7)})
    assert svc.check_and_notify(now=now)[0]["level"] == "escalation"


def test_recent_activity_no_notification():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1"], {"s1": now - timedelta(days=1)})
    assert svc.check_and_notify(now=now) == []


def test_only_idle_students_notified():
    now = datetime(2026, 11, 18, 12, 0, 0)
    svc = _svc(["s1", "s2"], {"s1": now - timedelta(days=4), "s2": now - timedelta(days=1)})
    sent = svc.check_and_notify(now=now)
    assert [x["studentId"] for x in sent] == ["s1"]
```

- [ ] **Step 2: 运行验证失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_message_channel.py tests/contexts/course_assistant/test_supervision.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `supervision.py` 常量、`MessageChannelPort`、`StubMessageChannel`、`SupervisionService`**

`supervision.py`：`IDLE_REMINDER_DAYS = 3`、`ESCALATION_DAYS = 7`、`IDLE_REMINDER_MESSAGE = "你已经好几天没有学习啦，记得回来继续学习哦。"`、`ESCALATION_MESSAGE = "你已超过一周未学习，请尽快回到课堂完成学习计划。"`。
`message_channel.py`：`StubMessageChannel.send` 生成 `"msg_" + uuid.uuid4().hex[:12]` 并追加到 `self.sent`。
`SupervisionService._detect(student_id, now) -> tuple[str, str] | None`：`last is None → (ESCALATION_MESSAGE, "escalation")`；`days >= 7 → escalation`；`days >= 3 → reminder`；否则 `None`。`check_and_notify` 遍历 `enrolled_student_ids()`，命中则 `send` 并收集结果。

- [ ] **Step 4: 运行验证通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/course_assistant/test_message_channel.py tests/contexts/course_assistant/test_supervision.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/course_assistant/domain/supervision.py contexts/course_assistant/domain/ports.py contexts/course_assistant/infrastructure/message_channel.py contexts/course_assistant/application/service.py tests/contexts/course_assistant/test_message_channel.py tests/contexts/course_assistant/test_supervision.py
git commit -m "feat(course-assistant): add supervision check and message channel"
```

---

### Task 7: API 装配 + 应用挂载

**Files:**
- Create: `contexts/course_assistant/interface/__init__.py`
- Create: `contexts/course_assistant/interface/schemas.py`
- Create: `contexts/course_assistant/interface/routes.py`
- Create: `contexts/course_assistant/interface/dependencies.py`
- Modify: `api/main.py`（`app.include_router(course_router)`）
- Test: `tests/test_course_api.py`

**Interfaces:**
- Consumes: `CourseAssistantService`、`SupervisionService`（Task 4–6）。
- Produces:
  - `PlanRequest(position: str, studentId: str | None = None)`
  - `router = APIRouter(prefix="/api/v1/course", tags=["course"])`，三端点：`POST /plan`、`POST /plan/refresh`、`POST /supervision/check`
  - `get_course_assistant_service(session=Depends(get_session))`、`get_supervision_service(session=Depends(get_session))`

- [ ] **Step 1: 写失败测试**

`tests/test_course_api.py`（内存 SQLite + dependency override，`_StubProgress` 复用 Task 4/5 写法；override 返回真实 `CourseAssistantService`/`SupervisionService`）：
```python
def test_course_plan_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/course/plan", json={"position": "大模型应用开发岗", "studentId": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["position"] == "大模型应用开发岗"
    assert body["data"]["items"][0]["courseId"]


def test_course_plan_validation_error():
    c = _client()
    r = c.post("/api/v1/course/plan", json={})
    assert r.status_code == 400
    assert r.json()["code"] == 40000


def test_course_refresh_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/course/plan/refresh", json={"position": "大模型应用开发岗", "studentId": "s1"})
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_supervision_check_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/course/supervision/check")
    assert r.status_code == 200
    assert r.json()["code"] == 0
    assert isinstance(r.json()["data"], list)
```

- [ ] **Step 2: 运行验证失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_course_api.py -v`
Expected: FAIL（`ImportError: contexts.course_assistant.interface` 或路由 404）

- [ ] **Step 3: 实现 `schemas.py`、`dependencies.py`、`routes.py`，改 `api/main.py`**

`schemas.py`：`PlanRequest(BaseModel)`（`position: str`、`studentId: str | None = None`）。
`dependencies.py`：模块级 `_path_knowledge = InMemoryPathKnowledge()`、`_message_channel = StubMessageChannel()`；`get_course_assistant_service` 返回 `CourseAssistantService(get_llm(get_settings()), _path_knowledge, CourseRepository(session))`；`get_supervision_service` 返回 `SupervisionService(CourseRepository(session), _message_channel)`。
`routes.py`：三端点，`plan`/`refresh` 调 `.to_dict()` 包进 `ok(data=..., trace_id=get_trace_id())`；`supervision/check` 直接 `ok(data=service.check_and_notify(), trace_id=get_trace_id())`。
`api/main.py`：`from contexts.course_assistant.interface.routes import router as course_router` + `app.include_router(course_router)`。

- [ ] **Step 4: 运行验证通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_course_api.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 全量测试**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: 全部通过（既有 129 + 新增 ~35）

- [ ] **Step 6: 提交**

```bash
git add contexts/course_assistant/interface/__init__.py contexts/course_assistant/interface/schemas.py contexts/course_assistant/interface/routes.py contexts/course_assistant/interface/dependencies.py api/main.py tests/test_course_api.py
git commit -m "feat(course-assistant): expose course and supervision APIs"
```

---

## Self-Review

- **Spec coverage**：FR-006（Task 4 生成计划）、FR-007（Task 5 重规划 + Task 7 绑定真实 ID）、FR-009（Task 6 督学 + 消息通道）全覆盖；无遗漏。
- **Step scan**：每步含测试名+断言或精确签名；无 TBD/「补充校验」类空话。
- **Type consistency**：`PathStep`/`PlanItem`/`LearningPlan`（Task 1）被 Task 2/4/5 一致使用；`ProgressPort` 五方法（Task 3）被 Task 4/5/6 一致消费；`MessageChannelPort`（Task 6）在 Task 7 装配一致。
- **Review Focus**：5 条各有对应测试（分别钉在 Task 4/4/6/5/4）。
- **Proportion**：计划以签名+断言为主，实现体仅在 join 算法/兜底文案处给一句说明；长度与 4 个新 API + 8 个新模块相称。

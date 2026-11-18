# 阶段 2 — 营销 Agent（sales_assistant）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地售前咨询 Agent：多轮对话识别学习方向/岗位 → 推荐课程 → 回答报名/学习 FAQ → 线索留资，端点 `POST /api/v1/sales/chat`。

**Architecture:** 单一限界上下文 `sales_assistant`，纯 Service + 端口（不引 LangGraph）。确定性逻辑（方向/岗位枚举归一化、FAQ 关键字匹配、课程查询、无匹配课程处理、留资写入）为纯函数/查表；LLM 只做意图识别、课程话术组织、FAQ 兜底、联系方式提取，结构化输出用 prompt + `json.loads` 解析（重试一次）。会话记忆走 `MemoryPort`（进程内 `InMemoryStore` 单例）；留资挂接 `VipReportPort`（stub）。跨上下文依赖方向：`sales_assistant` 只依赖 `shared` + 自身，不 import 其他 context。

**Tech Stack:** 复用阶段 0/1 的 Python 3.13.5、FastAPI、SQLAlchemy 2.x、Pydantic v2、`shared.infrastructure.llm`（DeepSeek/Fake）、`shared.infrastructure.memory`（InMemoryStore）。不新增依赖，不新增表（复用 `Lead` / `Course` / `CourseCategory`）。

**Spec:**
- `docs/superpowers/specs/2026-11-18-sales-assistant-design.md`（本计划实现的唯一权威设计，含第 8 节补充决策）
- `docs/码帮智 · 教育智能体平台需求规格说明书.md`（8.1 智能客服模块 FR-001~005、第 561/575-578 行规则）
- `docs/码帮智 · 教育智能体平台系统技术设计说明书.md`（5.2 营销 Agent、6.2 业务表/同步缓存表、8.1 售前咨询流程）

## Global Constraints

- Python 版本 ≥ 3.11（本机 3.13.5）；所有命令在 venv 内执行：`.venv/Scripts/python.exe -m pytest`（**不得**用 anaconda 全局 python）。
- 依赖方向严格单向：`contexts/* → shared/infrastructure → shared/common`；`sales_assistant` 只依赖 `shared` + 自身，不 import 其他 context。
- 统一响应结构 `{"code": int, "message": str, "data": Any, "traceId": str}`，成功 `code = 0`，经 `api.schemas.ok(data=..., trace_id=get_trace_id())`。
- LLM 默认 `fake`（`Settings.llm_provider` 默认值），测试/无 key 环境不得连真实 DeepSeek；`LLMPort.chat(messages) -> LLMResult` 纯文本，无 JSON mode / 无工具调用。
- 结构化输出（意图/联系方式）用 prompt + `json.loads` 解析，失败重试一次（共 2 次），仍失败走确定性兜底（意图→「方向未明→追问」；联系方式→「未提取到」）。
- 确定性逻辑（方向/岗位归一化、FAQ 匹配、课程查询、无匹配课程「如实告知+引导留资」）不得编造方向/课程。
- v1.0 明确不做：鉴权、向量库/RAG、LangGraph、真实 `report_vip` 外部调用（stub）、`ConversationMessage` 持久化。

## Review Focus

1. LLM 输出非法 JSON（意图识别或联系方式提取）时重试一次仍失败，应干净兜底到「方向未明→追问」/「未提取到联系方式」，不抛 500——测试：FakeLLM 返回非法 JSON 的 `chat` 不抛异常且返回 `DIRECTION_PROMPT`。
2. 记忆中的方向与本次 LLM 推断冲突时记忆优先，方向不得中途翻转——测试：记忆 `Java` + LLM 推断 `AI` → 返回 `Java`。
3. 无匹配课程时（direction/position 组合无 `Course` 行）必须走「如实告知 + 引导留资」，不编造课程、`courses` 为空——测试：无 `Course` 行 → `reply == NO_COURSE_REPLY` 且 `courses == []`。
4. 留资方向未知时 `Lead.direction` 为 NOT NULL，必须写 `"其他"` 而非 `None`/抛 DB 错误——测试：无方向留资 → `save_lead` 后 `direction == "其他"`。
5. `conversationId` 为空时服务端生成 `c_` 前缀 ID 并回传，二次请求复用同一记忆——测试：同一 `conversationId` 两次 `chat`，第二次读到第一次记忆的方向。

---

### Task 1: sales_assistant — 方向/岗位归一化 + FAQ 表（纯函数域）

**Files:**
- Create: `contexts/sales_assistant/domain/__init__.py`（空文件）
- Create: `contexts/sales_assistant/domain/directions.py`
- Test: `tests/contexts/sales_assistant/test_directions.py`

**Interfaces:**
- Produces（纯函数，无 IO、无 import shared/其他 context）：
  - `DIRECTIONS = ["Java", "前端", "AI", "其他"]`
  - `AI_POSITIONS = ["大模型算法岗", "大模型应用开发岗"]`
  - `normalize_direction(text: str | None) -> str | None`：归一化到 `DIRECTIONS` 四值之一，或返回 `None` 表示「方向未明」。`text` 为 `None`/空/未知 → `None`；显式「其他/没方向/不知道/不确定/没想好」→ `"其他"`。
  - `normalize_position(text: str | None) -> str | None`：归一化到 `AI_POSITIONS` 两值之一；未知/空返回 `None`。
  - `FAQ_ENROLLMENT: list[tuple[tuple[str, ...], str]]`（报名就业 FAQ 表）
  - `FAQ_STUDY: list[tuple[tuple[str, ...], str]]`（学习 FAQ 表）
  - `match_faq(message: str, faq_table: list[tuple[tuple[str, ...], str]]) -> str | None`：按序遍历，命中任意关键字（`any(k in message for k in keywords)`）返回对应答案；均未命中返回 `None`。

- [ ] **Step 1: 写失败测试**

`tests/contexts/sales_assistant/test_directions.py`：

```python
from contexts.sales_assistant.domain.directions import (
    normalize_direction,
    normalize_position,
    match_faq,
    FAQ_ENROLLMENT,
    FAQ_STUDY,
)


def test_normalize_direction_known():
    assert normalize_direction("想学Java") == "Java"
    assert normalize_direction("前端") == "前端"
    assert normalize_direction("人工智能") == "AI"
    assert normalize_direction("大模型") == "AI"


def test_normalize_direction_no_direction():
    assert normalize_direction("我没方向") == "其他"
    assert normalize_direction("不知道") == "其他"


def test_normalize_direction_unclear_returns_none():
    assert normalize_direction("") is None
    assert normalize_direction(None) is None
    assert normalize_direction("随便") is None


def test_normalize_position_known():
    assert normalize_position("大模型算法岗") == "大模型算法岗"
    assert normalize_position("算法岗") == "大模型算法岗"
    assert normalize_position("应用开发") == "大模型应用开发岗"


def test_normalize_position_unknown_returns_none():
    assert normalize_position("随便") is None
    assert normalize_position("") is None
    assert normalize_position(None) is None


def test_match_faq_enrollment_flow_exact_answer():
    assert match_faq("报名流程是什么", FAQ_ENROLLMENT) == "报名流程：1) 在线提交报名信息；2) 顾问老师电话/微信确认；3) 缴费开通课程；4) 进入班级群开始学习。"


def test_match_faq_enrollment_job():
    assert match_faq("包就业吗", FAQ_ENROLLMENT) == FAQ_ENROLLMENT[1][1]


def test_match_faq_study_period():
    assert match_faq("学习周期多久", FAQ_STUDY) == FAQ_STUDY[1][1]


def test_match_faq_miss_returns_none():
    assert match_faq("今天天气如何", FAQ_ENROLLMENT) is None
    assert match_faq("今天天气如何", FAQ_STUDY) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/sales_assistant/test_directions.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.sales_assistant.domain.directions'`）

- [ ] **Step 3: 实现 `contexts/sales_assistant/domain/directions.py`**

`normalize_direction` 用子串匹配（`t = (text or "").strip().lower()`；`text` 为空/`None` 直接返回 `None`）：含 `"java"`/`"后端"` → `"Java"`；含 `"前端"`/`"web"`/`"网页"` → `"前端"`；含 `"ai"`/`"人工智能"`/`"大模型"` → `"AI"`；含 `"其他"`/`"没方向"`/`"不知道"`/`"不确定"`/`"没想好"` → `"其他"`；否则返回 `None`。

`normalize_position`（`t` 同上）：含 `"算法"` → `"大模型算法岗"`；含 `"应用开发"`/`"开发"`/`"应用"` → `"大模型应用开发岗"`；否则 `None`（`text` 空/`None` 直接返回 `None`）。

FAQ 表（确定性文案，与测试 Step 1 的断言一致）：

```python
FAQ_ENROLLMENT = [
    (("报名", "入学", "流程"), "报名流程：1) 在线提交报名信息；2) 顾问老师电话/微信确认；3) 缴费开通课程；4) 进入班级群开始学习。"),
    (("包就业", "就业", "内推", "薪资"), "我们提供就业指导服务（简历优化、模拟面试、岗位内推），但不承诺包就业。"),
]

FAQ_STUDY = [
    (("自学", "自己学"), "可以自学，平台提供录播课、题库与答疑服务；想系统高效学习建议跟班，有老师答疑和督学。"),
    (("周期", "多久", "多长时间"), "学习周期因方向与基础而异：全日制约 4-6 个月，业余学习约 6-12 个月。"),
]
```

`match_faq` 按序遍历 `faq_table`，`any(k in message for k in keywords)` 命中即返回答案；否则 `None`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/sales_assistant/test_directions.py -v`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/sales_assistant/domain/__init__.py contexts/sales_assistant/domain/directions.py tests/contexts/sales_assistant/test_directions.py
git commit -m "feat: add sales assistant direction/FAQ domain rules"
```

---

### Task 2: sales_assistant — 端口 + 仓库（VipReportPort / SalesRepository）

**Files:**
- Create: `contexts/sales_assistant/domain/ports.py`
- Create: `contexts/sales_assistant/infrastructure/__init__.py`（空文件）
- Create: `contexts/sales_assistant/infrastructure/vip_report.py`
- Create: `contexts/sales_assistant/infrastructure/repository.py`
- Test: `tests/contexts/sales_assistant/test_repository.py`

**Interfaces:**
- Consumes: `shared.infrastructure.db.models.business.Lead`、`shared.infrastructure.db.models.sync_cache.Course`、`sqlalchemy.orm.Session`。
- Produces:
  - `VipReportPort`（Protocol）：`report_vip(self, lead: Lead) -> bool`。
  - `StubVipReport`：实现 `report_vip`，恒返回 `True`。
  - `SalesRepository(session: Session)`：
    - `find_courses(self, direction: str, position: str | None = None) -> list[dict]`：返回 `[{"courseId", "name", "price", "durationHours", "highlights"}]`。
    - `save_lead(self, contact: str, direction: str, position: str | None, remark: str | None, source: str) -> Lead`：写库并 `commit`，返回 `Lead`。

- [ ] **Step 1: 写失败测试**

`tests/contexts/sales_assistant/test_repository.py`：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Course
from shared.infrastructure.db.models.business import Lead
from contexts.sales_assistant.infrastructure.repository import SalesRepository


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_find_courses_by_direction():
    s = _session()
    s.add(Course(course_id="c1", name="Java入门", price=100, duration_hours=20, highlights="h", direction="Java", position=None))
    s.add(Course(course_id="c2", name="AI算法", price=200, duration_hours=30, highlights="h", direction="AI", position="大模型算法岗"))
    s.commit()
    rows = SalesRepository(s).find_courses("Java")
    assert len(rows) == 1
    assert rows[0]["courseId"] == "c1"
    assert rows[0]["price"] == 100.0


def test_find_courses_by_direction_and_position():
    s = _session()
    s.add(Course(course_id="c2", name="AI算法", price=200, duration_hours=30, highlights="h", direction="AI", position="大模型算法岗"))
    s.add(Course(course_id="c3", name="AI应用", price=300, duration_hours=40, highlights="h", direction="AI", position="大模型应用开发岗"))
    s.commit()
    rows = SalesRepository(s).find_courses("AI", "大模型算法岗")
    assert len(rows) == 1
    assert rows[0]["courseId"] == "c2"


def test_find_courses_no_match_returns_empty():
    s = _session()
    assert SalesRepository(s).find_courses("前端") == []


def test_save_lead_persists():
    s = _session()
    lead = SalesRepository(s).save_lead("13800138000", "AI", "大模型算法岗", "备注", "web")
    assert lead.lead_id.startswith("lead_")
    assert lead.direction == "AI"
    fetched = s.get(Lead, lead.lead_id)
    assert fetched is not None
    assert fetched.contact == "13800138000"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/sales_assistant/test_repository.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.sales_assistant.infrastructure.repository'`）

- [ ] **Step 3: 实现端口与仓库**

`contexts/sales_assistant/domain/ports.py`：

```python
from typing import Protocol

from shared.infrastructure.db.models.business import Lead


class VipReportPort(Protocol):
    def report_vip(self, lead: Lead) -> bool: ...
```

`contexts/sales_assistant/infrastructure/vip_report.py`：

```python
from shared.infrastructure.db.models.business import Lead


class StubVipReport:
    def report_vip(self, lead: Lead) -> bool:
        return True
```

`contexts/sales_assistant/infrastructure/repository.py`：`find_courses` 用 `select(Course).where(Course.direction == direction)`，`position` 非空时追加 `.where(Course.position == position)`；每行映射 `courseId=c.course_id`、`name=c.name`、`price=float(c.price) if c.price is not None else 0.0`、`durationHours=c.duration_hours or 0`、`highlights=c.highlights or ""`。`save_lead` 生成 `lead_id = "lead_" + uuid.uuid4().hex[:12]`，构造 `Lead(...)`、`add`、`commit`、返回该 `Lead`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/sales_assistant/test_repository.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/sales_assistant/domain/ports.py contexts/sales_assistant/infrastructure/__init__.py contexts/sales_assistant/infrastructure/vip_report.py contexts/sales_assistant/infrastructure/repository.py tests/contexts/sales_assistant/test_repository.py
git commit -m "feat: add sales assistant repository and vip report port"
```

---

### Task 3: sales_assistant — SalesChatService 编排

**Files:**
- Create: `contexts/sales_assistant/application/__init__.py`（空文件）
- Create: `contexts/sales_assistant/application/service.py`
- Test: `tests/contexts/sales_assistant/test_service.py`

**Interfaces:**
- Consumes: Task 1 的 `directions`（`normalize_direction`/`normalize_position`/`match_faq`/`FAQ_ENROLLMENT`/`FAQ_STUDY`）、Task 2 的 `VipReportPort`/`SalesRepository`；`shared.infrastructure.llm.port.LLMPort`、`shared.infrastructure.memory.port.MemoryPort`。
- Produces:
  - `SalesChatService(llm: LLMPort, memory: MemoryPort, repo: SalesRepository, vip_report: VipReportPort)`
  - `chat(self, conversation_id: str | None, message: str, source: str) -> dict`：返回 `{"conversationId", "reply", "direction", "position", "courses", "leadSaved"}`。
  - 模块级常量（确定性回复文案，测试断言引用）：`DIRECTION_PROMPT`、`AI_POSITION_PROMPT`、`NO_DIRECTION_PROMPT`、`NO_COURSE_REPLY`、`LEAD_ASK_CONTACT_REPLY`、`LEAD_SAVED_REPLY`。

- [ ] **Step 1: 写失败测试**

`tests/contexts/sales_assistant/test_service.py`：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Course
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.memory.in_memory import InMemoryStore

from contexts.sales_assistant.application.service import (
    SalesChatService,
    DIRECTION_PROMPT,
    NO_COURSE_REPLY,
    LEAD_ASK_CONTACT_REPLY,
)
from contexts.sales_assistant.domain.directions import FAQ_ENROLLMENT
from contexts.sales_assistant.infrastructure.repository import SalesRepository
from contexts.sales_assistant.infrastructure.vip_report import StubVipReport


def _service(responses, courses=()):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(engine)
    for c in courses:
        s.add(Course(**c))
    s.commit()
    return SalesChatService(
        FakeLLMAdapter(responses=responses),
        InMemoryStore(),
        SalesRepository(s),
        StubVipReport(),
    )


def test_chat_direction_guide_when_unknown():
    svc = _service(['{"intent": "course_intro", "direction": "", "position": ""}'])
    r = svc.chat(None, "想学编程", "web")
    assert r["reply"] == DIRECTION_PROMPT
    assert r["courses"] == []
    assert r["leadSaved"] is False
    assert r["conversationId"].startswith("c_")


def test_chat_course_intro_matched():
    svc = _service(
        ['{"intent": "course_intro", "direction": "AI", "position": "大模型算法岗"}', "这是推荐话术"],
        courses=[dict(course_id="c1", name="AI算法课", price=100, duration_hours=20, highlights="h", direction="AI", position="大模型算法岗")],
    )
    r = svc.chat(None, "想学AI算法", "web")
    assert r["reply"] == "这是推荐话术"
    assert r["courses"][0]["courseId"] == "c1"
    assert r["direction"] == "AI"
    assert r["position"] == "大模型算法岗"


def test_chat_course_intro_no_match():
    svc = _service(['{"intent": "course_intro", "direction": "前端", "position": ""}'])
    r = svc.chat(None, "想学前端", "web")
    assert r["reply"] == NO_COURSE_REPLY
    assert r["courses"] == []


def test_chat_faq_hit_deterministic():
    svc = _service(['{"intent": "enrollment_faq", "direction": "", "position": ""}'])
    r = svc.chat(None, "报名流程是什么", "web")
    assert r["reply"] == FAQ_ENROLLMENT[0][1]


def test_chat_faq_miss_llm_fallback():
    svc = _service(['{"intent": "study_faq", "direction": "", "position": ""}', "学习建议（LLM）"])
    r = svc.chat(None, "如何高效学习", "web")
    assert r["reply"] == "学习建议（LLM）"


def test_chat_lead_with_contact():
    svc = _service([
        '{"intent": "lead_capture", "direction": "AI", "position": "大模型算法岗"}',
        '{"contact": "wx123", "remark": "想学AI"}',
    ])
    r = svc.chat(None, "我微信是wx123", "web")
    assert r["leadSaved"] is True
    assert r["direction"] == "AI"


def test_chat_lead_without_contact():
    svc = _service([
        '{"intent": "lead_capture", "direction": "", "position": ""}',
        '{"contact": "", "remark": ""}',
    ])
    r = svc.chat(None, "我想报名", "web")
    assert r["leadSaved"] is False
    assert r["reply"] == LEAD_ASK_CONTACT_REPLY


def test_chat_lead_unknown_direction_writes_other():
    svc = _service([
        '{"intent": "lead_capture", "direction": "", "position": ""}',
        '{"contact": "13800138000", "remark": ""}',
    ])
    r = svc.chat(None, "电话13800138000", "web")
    assert r["leadSaved"] is True
    assert r["direction"] == "其他"


def test_chat_memory_precedence():
    svc = _service([
        '{"intent": "enrollment_faq", "direction": "Java", "position": ""}',
        '{"intent": "enrollment_faq", "direction": "AI", "position": "大模型算法岗"}',
    ])
    r1 = svc.chat(None, "报名流程", "web")
    r2 = svc.chat(r1["conversationId"], "包就业吗", "web")
    assert r2["direction"] == "Java"


def test_chat_bad_json_falls_back_to_guide():
    svc = _service(["not json", "still not json"])
    r = svc.chat(None, "想学编程", "web")
    assert r["reply"] == DIRECTION_PROMPT
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/sales_assistant/test_service.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'contexts.sales_assistant.application.service'`）

- [ ] **Step 3: 实现 `contexts/sales_assistant/application/service.py`**

模块级常量（测试 Step 1 引用）：
```python
DIRECTION_PROMPT = "请问你想学习哪个方向？可选：Java、前端、AI。如果还不确定，也可以直接找老师咨询。"
AI_POSITION_PROMPT = "AI 方向有两个岗位方向：大模型算法岗、大模型应用开发岗。你对哪个更感兴趣？"
NO_DIRECTION_PROMPT = "好的，你可以直接找老师咨询，也可以留下联系方式，我们安排老师为你介绍。"
NO_COURSE_REPLY = "抱歉，暂未找到与你方向/岗位匹配的课程。你可以留下联系方式（电话/微信），我们安排顾问老师为你介绍。"
LEAD_ASK_CONTACT_REPLY = "请留下你的联系方式（电话/微信），我们会安排顾问老师尽快联系你。"
LEAD_SAVED_REPLY = "已为你登记，顾问老师会尽快联系你。"
```

意图识别 prompt 的 JSON schema（LLM 输出键值固定）：
- intent 取值：`direction_guide | course_intro | enrollment_faq | study_faq | lead_capture`
- `direction`（自由文本，归一化兜底）、`position`（自由文本，归一化兜底）

`chat` 编排流程（每个 LLM 调用重试一次）：
1. `conv_id = conversation_id or "c_" + uuid.uuid4().hex[:12]`；`state = self._memory.get(conv_id) or {}`。
2. `intent = self._recognize_intent(message, state)`（LLM → JSON；失败返回 `{"intent": "direction_guide", "direction": None, "position": None}`）。
3. 合并（记忆优先）：`direction = state.get("direction") or normalize_direction(intent.get("direction"))`；`position = state.get("position") or normalize_position(intent.get("position"))`。
4. 分支（intent 值）：
   - `lead_capture` → `_handle_lead`：`direction = direction or "其他"`；LLM 提取 `{"contact", "remark"}`；`contact` 空 → 回复 `LEAD_ASK_CONTACT_REPLY`、`leadSaved=False`；否则 `repo.save_lead(...)` + `vip_report.report_vip(lead)`（尽力而为），回复 `LEAD_SAVED_REPLY`、`leadSaved=True`。
   - `enrollment_faq`/`study_faq` → `_handle_faq`：`match_faq(message, FAQ_ENROLLMENT 或 FAQ_STUDY)`；未命中 → LLM 兜底纯文本。
   - `course_intro` → `direction` 为 `None`/`"其他"`，或 `direction == "AI"` 且 `position is None` → 走引导（`_guidance_reply`）；否则 `repo.find_courses(direction, position)`；空 → 回复 `NO_COURSE_REPLY`、`courses=[]`；非空 → LLM 组织话术（输入 `json.dumps(courses)`，纯文本输出）。
   - 其他（`direction_guide`/未知）→ 引导。
5. `_guidance_reply(direction, position)`：`None` → `DIRECTION_PROMPT`；`"其他"` → `NO_DIRECTION_PROMPT`；`"AI"` 且 `position is None` → `AI_POSITION_PROMPT`；否则 `f"已了解你的方向：{direction}"`（+岗位）。
6. 每次分支结束后 `_save_state(conv_id, direction, position)`（`memory.set(conv_id, {"direction": direction, "position": position})`），返回 `{"conversationId": conv_id, "reply": ..., "direction": direction, "position": position, "courses": [...], "leadSaved": bool}`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/contexts/sales_assistant/test_service.py -v`
Expected: PASS（10 passed）

- [ ] **Step 5: 提交**

```bash
git add contexts/sales_assistant/application/__init__.py contexts/sales_assistant/application/service.py tests/contexts/sales_assistant/test_service.py
git commit -m "feat: add sales chat service orchestration"
```

---

### Task 4: API 装配（schema / route / dependency / main）

**Files:**
- Create: `api/schemas/sales.py`
- Create: `api/routes/sales.py`
- Modify: `api/dependencies.py`（新增 `_sales_memory` 单例 + `get_sales_chat_service`）
- Modify: `api/main.py`（`include_router(sales_router)`）
- Test: `tests/test_sales_api.py`

**Interfaces:**
- Consumes: Task 3 的 `SalesChatService`；`api.schemas.ok`、`api.handlers`、`shared.infrastructure.observability.tracing.get_trace_id`。
- Produces: `POST /api/v1/sales/chat`；请求体 `SalesChatRequest {conversationId: str|None, message: str, source: str}`；响应 `ok(data=service.chat(...))`。

- [ ] **Step 1: 写失败测试**

`tests/test_sales_api.py`：

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Course
from api.main import create_app
from api.dependencies import get_sales_chat_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.memory.in_memory import InMemoryStore
from contexts.sales_assistant.application.service import SalesChatService
from contexts.sales_assistant.infrastructure.repository import SalesRepository
from contexts.sales_assistant.infrastructure.vip_report import StubVipReport


def _client(responses=None, seed=None):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(engine)
    if seed:
        seed(s)
        s.commit()

    def override_session():
        yield s

    def override_service():
        return SalesChatService(
            FakeLLMAdapter(responses=responses),
            InMemoryStore(),
            SalesRepository(s),
            StubVipReport(),
        )

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_sales_chat_service] = override_service
    return TestClient(app)


def test_sales_chat_endpoint_ok():
    def seed(s):
        s.add(Course(course_id="c1", name="AI算法课", price=100, duration_hours=20, highlights="h", direction="AI", position="大模型算法岗"))

    c = _client(
        responses=['{"intent": "course_intro", "direction": "AI", "position": "大模型算法岗"}', "推荐话术"],
        seed=seed,
    )
    r = c.post("/api/v1/sales/chat", json={"message": "想学AI", "source": "web"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["conversationId"].startswith("c_")
    assert body["data"]["courses"][0]["courseId"] == "c1"


def test_sales_chat_endpoint_validation_error():
    c = _client()
    r = c.post("/api/v1/sales/chat", json={})
    assert r.status_code == 400
    assert r.json()["code"] == 40000
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sales_api.py -v`
Expected: FAIL（`ImportError: cannot import name 'get_sales_chat_service'`）

- [ ] **Step 3: 实现 API 装配**

`api/schemas/sales.py`：

```python
from pydantic import BaseModel


class SalesChatRequest(BaseModel):
    conversationId: str | None = None
    message: str
    source: str = "web"
```

`api/routes/sales.py`：`router = APIRouter(prefix="/api/v1/sales", tags=["sales"])`；`@router.post("/chat")` 接收 `body: SalesChatRequest` + `service: SalesChatService = Depends(get_sales_chat_service)`，返回 `ok(data=service.chat(body.conversationId, body.message, body.source), trace_id=get_trace_id())`。

`api/dependencies.py` 追加：模块级 `_sales_memory = InMemoryStore()`；`get_sales_chat_service(session: Session = Depends(get_session)) -> SalesChatService` 返回 `SalesChatService(llm=get_llm(get_settings()), memory=_sales_memory, repo=SalesRepository(session), vip_report=StubVipReport())`。

`api/main.py` 追加 `from api.routes.sales import router as sales_router` + `app.include_router(sales_router)`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sales_api.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 全量测试 + 提交**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全量通过（阶段 1 的 76 个 + 本阶段新增，无失败）

```bash
git add api/schemas/sales.py api/routes/sales.py api/dependencies.py api/main.py tests/test_sales_api.py
git commit -m "feat: add sales chat api endpoint"
```

# 阶段 0 — 工程骨架 + 共享基础设施 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可运行的 DDD 模块化单体骨架与共享基础设施，为后续各业务上下文（自主练习、营销、助教等）提供统一的地基。

**Architecture:** 按技术设计说明书 3.5 的目录组织，依赖方向严格单向 `contexts/* → shared/infrastructure → shared/common`；本地轻量优先，以 Port（Protocol）+ Adapter 抽象数据库/LLM/记忆，阶段 0 用 SQLite + Fake/DeepSeek LLM + 内存记忆，后续切换 MySQL/真实 LLM 只换 Adapter。

**Tech Stack:** Python 3.13.5、FastAPI、SQLAlchemy 2.x + Alembic、Pydantic v2 + pydantic-settings、langchain-openai（DeepSeek 端点）、structlog、pytest + httpx、import-linter。

**Spec:**
- `docs/superpowers/specs/2026-11-17-implementation-phasing-design.md`（本计划的阶段 0 详细设计）
- `docs/码帮智 · 教育智能体平台系统技术设计说明书.md`（3.5 目录结构、6.2 表设计、7.1 响应结构）

## Global Constraints

- Python 版本 ≥ 3.11（本机 3.13.5）；若 langchain-openai 在 3.13 安装失败，降级用 3.12 venv。
- 依赖方向严格单向：`contexts/* → shared/infrastructure → shared/common`；context 之间禁止互相依赖；`shared` 不得依赖 `contexts/orchestrator/api`。
- 统一响应结构 `{"code": int, "message": str, "data": Any, "traceId": str}`，成功 `code = 0`。
- 本地轻量优先：数据库默认 `sqlite:///./data/app.db`；LLM 默认 `fake`（`.env.example` 中示例 `deepseek`）；记忆用内存实现。
- 所有命令在 venv 内执行：`source .venv/Scripts/activate && <cmd>`。

## Review Focus

1. 中文/非 ASCII 文本被 JSON 序列化转义成 `\uXXXX`——`JsonUtil.dumps` 必须 `ensure_ascii=False`。
2. 无 `X-Trace-Id` 请求头时，响应缺少 traceId 或未回写响应头——traceId 中间件须生成并回写。
3. 测试/无 key 环境误连真实 DeepSeek API——`Settings.llm_provider` 默认 `fake`。
4. 18 张表（同步缓存 10 + 业务 8）建表遗漏——测试断言表名全集。
5. 骨架期就引入 context 间或反向依赖——import-linter 的 layers + independence 合约守住。

---

### Task 1: 工程骨架与依赖

**Files:**
- Create: `pyproject.toml`、`.gitignore`、`.env.example`、`README.md`、`alembic.ini`
- Create 包骨架（含空 `__init__.py`）：
  - `shared/__init__.py`、`shared/common/__init__.py`、`shared/common/util/__init__.py`、`shared/common/exception/__init__.py`
  - `shared/infrastructure/__init__.py`、`shared/infrastructure/llm/__init__.py`、`shared/infrastructure/db/__init__.py`、`shared/infrastructure/db/models/__init__.py`、`shared/infrastructure/memory/__init__.py`、`shared/infrastructure/observability/__init__.py`、`shared/infrastructure/tool_registry/__init__.py`
  - `contexts/__init__.py` 及 7 个子包：`sales_assistant`、`teaching_assistant`、`course_assistant`、`exam_paper_generation`、`self_practice`、`exam_grading`、`learning_analytics`（各一个空 `__init__.py`）
  - `orchestrator/__init__.py`、`api/__init__.py`、`api/routes/__init__.py`、`tests/__init__.py`、`tests/conftest.py`

**Interfaces:**
- Produces: 可导入的顶层包 `shared`、`contexts`、`orchestrator`、`api`；venv 内可运行 `pytest`。

- [ ] **Step 1: 初始化 git 与 venv**

```bash
cd "D:/projects/项目阶段/ai-assistant-platform"
git init
python -m venv .venv
```

- [ ] **Step 2: 写 `pyproject.toml`**

`[project]` name=`ai-assistant-platform`, version=`0.1.0`, requires-python=`>=3.11`；dependencies 含 `fastapi>=0.115`、`uvicorn[standard]>=0.30`、`sqlalchemy>=2.0`、`alembic>=1.13`、`pydantic>=2.7`、`pydantic-settings>=2.3`、`langchain-openai>=0.2`、`structlog>=24.1`；`[project.optional-dependencies].dev` 含 `pytest>=8.0`、`pytest-asyncio>=0.23`、`httpx>=0.27`、`import-linter>=2.0`。设置 `[tool.pytest.ini_options] testpaths=["tests"]`。

- [ ] **Step 3: 写 `.gitignore`、`.env.example`、`README.md`**

`.gitignore` 忽略 `.venv/`、`__pycache__/`、`*.pyc`、`.env`、`data/`、`.pytest_cache/`。`.env.example` 含注释掉的 `LLM_PROVIDER=deepseek`、`DEEPSEEK_API_KEY=`、`DATABASE_URL=sqlite:///./data/app.db`。README 一段话说明项目与启动方式。

- [ ] **Step 4: 创建上述全部包目录与空 `__init__.py`**

- [ ] **Step 5: 安装依赖并验证可运行**

```bash
source .venv/Scripts/activate && pip install -e ".[dev]"
```

Expected: 安装成功；`source .venv/Scripts/activate && python -c "import fastapi, sqlalchemy, pydantic, structlog; print('ok')"` 输出 `ok`。

- [ ] **Step 6: 验证 pytest 可运行**

```bash
source .venv/Scripts/activate && pytest -q
```

Expected: `no tests ran` 或 `0 passed`（无报错退出）。

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "chore: bootstrap project skeleton and dependencies"
```

---

### Task 2: shared/common/util 工具类

**Files:**
- Create: `shared/common/util/string_util.py`、`shared/common/util/json_util.py`、`shared/common/util/date_util.py`
- Test: `tests/common/test_string_util.py`、`tests/common/test_json_util.py`、`tests/common/test_date_util.py`

**Interfaces:**
- Produces:
  - `StringUtil.is_blank(value: str | None) -> bool`、`StringUtil.strip_to_none(value: str | None) -> str | None`、`StringUtil.truncate(value: str, max_len: int, suffix: str = "...") -> str`
  - `JsonUtil.dumps(value: Any) -> str`、`JsonUtil.loads(value: str, default: Any = None) -> Any`
  - `DateUtil.now() -> datetime`、`DateUtil.now_iso() -> str`、`DateUtil.to_iso(dt: datetime) -> str`

- [ ] **Step 1: 写失败测试**

`tests/common/test_string_util.py`：
```python
from shared.common.util.string_util import StringUtil

def test_is_blank():
    assert StringUtil.is_blank(None) is True
    assert StringUtil.is_blank("") is True
    assert StringUtil.is_blank("   ") is True
    assert StringUtil.is_blank("x") is False

def test_strip_to_none():
    assert StringUtil.strip_to_none("  ") is None
    assert StringUtil.strip_to_none(" a ") == "a"

def test_truncate():
    assert StringUtil.truncate("hi", 5) == "hi"
    assert StringUtil.truncate("hello world", 5) == "hello..."
```

`tests/common/test_json_util.py`：
```python
from shared.common.util.json_util import JsonUtil

def test_roundtrip():
    assert JsonUtil.loads(JsonUtil.dumps({"a": 1})) == {"a": 1}

def test_dumps_no_ascii_escape():
    assert "中文" in JsonUtil.dumps({"a": "中文"})

def test_loads_invalid_returns_default():
    assert JsonUtil.loads("{bad json", default=None) is None
```

`tests/common/test_date_util.py`：
```python
import re
from datetime import datetime, timezone
from shared.common.util.date_util import DateUtil

def test_now_iso_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*", DateUtil.now_iso())

def test_to_iso():
    dt = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert DateUtil.to_iso(dt) == "2026-11-17T12:00:00+00:00"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/common -q`
Expected: 全部 FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 实现三个工具类**

`JsonUtil.dumps` 用 `json.dumps(value, ensure_ascii=False, default=str)`；`JsonUtil.loads` 用 `json.loads` 捕获 `(json.JSONDecodeError, TypeError, ValueError)` 返回 `default`；`DateUtil.now_iso`/`to_iso` 输出 ISO 8601（`to_iso` 用 `dt.isoformat()`，`now()` 用 `datetime.now(timezone.utc)`）。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/common -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/common shared/common/util && git commit -m "feat: add shared common util classes"
```

---

### Task 3: shared/common/exception 统一异常体系

**Files:**
- Create: `shared/common/exception/codes.py`、`shared/common/exception/base.py`
- Test: `tests/common/test_exception.py`

**Interfaces:**
- Produces:
  - `ErrorCode(IntEnum)`：`SUCCESS=0`、`BAD_REQUEST=40000`、`UNAUTHORIZED=40100`、`FORBIDDEN=40300`、`NOT_FOUND=40400`、`INTERNAL=50000`、`LLM_UNAVAILABLE=50001`
  - `AppException(Exception)`：构造 `__init__(self, code: ErrorCode, message: str, http_status: int | None = None)`，属性 `.code`/`.message`/`.http_status`
  - `BadRequestError`、`UnauthorizedError`、`ForbiddenError`、`NotFoundError`、`InternalError`、`LLMUnavailableError`（各子类默认映射到对应 `ErrorCode` 与 `http_status`）

- [ ] **Step 1: 写失败测试**

`tests/common/test_exception.py`：
```python
import pytest
from shared.common.exception.codes import ErrorCode
from shared.common.exception.base import NotFoundError, AppException, InternalError

def test_error_code_values():
    assert ErrorCode.SUCCESS == 0
    assert ErrorCode.NOT_FOUND == 40400
    assert ErrorCode.INTERNAL == 50000

def test_not_found_defaults():
    e = NotFoundError("chapter not found")
    assert e.code == ErrorCode.NOT_FOUND
    assert e.message == "chapter not found"
    assert e.http_status == 404

def test_is_exception():
    with pytest.raises(AppException):
        raise InternalError("boom")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/common/test_exception.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 `codes.py` 与 `base.py`**

`AppException` 中 `http_status` 缺省时由子类给出；子类通过类属性 `default_http_status` 与 `default_code` 映射。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/common/test_exception.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/common/test_exception.py shared/common/exception && git commit -m "feat: add unified exception and error codes"
```

---

### Task 4: shared/infrastructure/config 配置

**Files:**
- Create: `shared/infrastructure/config.py`
- Test: `tests/infrastructure/test_config.py`

**Interfaces:**
- Produces:
  - `Settings(BaseSettings)` 字段：`app_name: str = "ai-assistant-platform"`、`env: str = "dev"`、`database_url: str = "sqlite:///./data/app.db"`、`llm_provider: Literal["deepseek", "fake"] = "fake"`、`deepseek_api_key: str = ""`、`deepseek_base_url: str = "https://api.deepseek.com"`、`deepseek_model: str = "deepseek-chat"`、`llm_timeout_seconds: int = 60`、`llm_max_retries: int = 1`；`model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
  - `get_settings() -> Settings`（`lru_cache` 包装）

- [ ] **Step 1: 写失败测试**

`tests/infrastructure/test_config.py`：
```python
from shared.infrastructure.config import Settings

def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "fake"
    assert s.database_url == "sqlite:///./data/app.db"

def test_env_overrides(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    s = Settings(_env_file=None)
    assert s.llm_provider == "deepseek"
    assert s.deepseek_api_key == "sk-test"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_config.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 `Settings` 与 `get_settings`**

用 `pydantic_settings.BaseSettings`；`get_settings` 用 `functools.lru_cache` 返回单例。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_config.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/infrastructure/test_config.py shared/infrastructure/config.py && git commit -m "feat: add pydantic settings"
```

---

### Task 5: shared/infrastructure/llm LLM 客户端封装

**Files:**
- Create: `shared/infrastructure/llm/port.py`、`shared/infrastructure/llm/fake.py`、`shared/infrastructure/llm/deepseek.py`、`shared/infrastructure/llm/factory.py`
- Test: `tests/infrastructure/test_llm.py`

**Interfaces:**
- Consumes: `Settings`（Task 4）
- Produces:
  - `LLMResult`（dataclass）：`content: str`、`prompt_tokens: int = 0`、`completion_tokens: int = 0`
  - `LLMPort(Protocol)`：`chat(self, messages: list[dict[str, str]]) -> LLMResult`
  - `FakeLLMAdapter`：`__init__(self, responses: list[str] | None = None)`；`chat` 按调用次数顺序返回 `responses`（耗尽则重复最后一条）
  - `DeepSeekAdapter`：`__init__(self, api_key: str, base_url: str, model: str, timeout: int, max_retries: int)`；`chat` 用 `langchain_openai.ChatOpenAI(api_key=..., base_url=..., model=..., timeout=..., max_retries=...)` 调 `invoke`
  - `get_llm(settings: Settings) -> LLMPort`：`llm_provider == "fake"` 返回 `FakeLLMAdapter`，`"deepseek"` 返回 `DeepSeekAdapter`

- [ ] **Step 1: 写失败测试**

`tests/infrastructure/test_llm.py`：
```python
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.llm.deepseek import DeepSeekAdapter
from shared.infrastructure.llm.factory import get_llm
from shared.infrastructure.config import Settings

def test_fake_returns_responses_in_order():
    llm = FakeLLMAdapter(responses=["a", "b"])
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "a"
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "b"
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "b"

def test_factory_fake():
    llm = get_llm(Settings(_env_file=None, llm_provider="fake"))
    assert isinstance(llm, FakeLLMAdapter)

def test_factory_deepseek():
    llm = get_llm(Settings(_env_file=None, llm_provider="deepseek", deepseek_api_key="sk-x"))
    assert isinstance(llm, DeepSeekAdapter)
    assert llm._model == "deepseek-chat"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_llm.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 port/fake/deepseek/factory**

`DeepSeekAdapter` 构造时保存 `self._model = model`，并惰性创建 `ChatOpenAI`（不在 `__init__` 就发起网络）；`chat` 从 `AIMessage.response_metadata` 尽力提取 token 用量（取不到则 0）。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_llm.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/infrastructure/test_llm.py shared/infrastructure/llm && git commit -m "feat: add LLM client port with deepseek and fake adapters"
```

---

### Task 6: shared/infrastructure/db 数据模型与 Alembic 迁移

**Files:**
- Create: `shared/infrastructure/db/base.py`、`shared/infrastructure/db/session.py`、`shared/infrastructure/db/models/sync_cache.py`、`shared/infrastructure/db/models/business.py`
- Modify: `shared/infrastructure/db/models/__init__.py`（导入全部模型类，使 `Base.metadata` 注册完整）
- Create: `alembic/env.py`、`alembic/script.py.mako`、`alembic/versions/0001_initial.py`
- Test: `tests/infrastructure/test_db.py`

**Interfaces:**
- Consumes: `Settings`（Task 4）
- Produces:
  - `Base(DeclarativeBase)`
  - `create_engine_and_session_factory(url: str) -> tuple[Engine, sessionmaker[Session]]`
  - `get_session(request) -> Generator[Session, None, None]`（FastAPI 依赖，读 `Settings` 构造单例 engine/session）
  - 20 张表的 ORM 模型（表名与列按技术设计 6.2）

**表清单（列以技术设计 6.2 为准）**：`course_category`、`course`、`chapter`、`video`、`video_annotation`、`student`、`teacher`、`student_teacher_relation`、`student_course`、`student_video_progress`（以上同步缓存）；`lead`、`practice_session`、`practice_question`、`practice_answer`、`learning_profile`、`mastery_trend`、`weak_point`、`conversation_message`（业务）。共 18 张（`teacher`/`student_teacher_relation`/`student_course` 在文档 6.2.1 仅列关键字段，按 `teacher_id PK/name`、`id PK/student_id/teacher_id`、`id PK/student_id/course_id/purchased_at` 建）。

- [ ] **Step 1: 写失败测试**

`tests/infrastructure/test_db.py`：
```python
from sqlalchemy import create_engine
from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401  触发模型注册

EXPECTED_TABLES = {
    "course_category", "course", "chapter", "video", "video_annotation",
    "student", "teacher", "student_teacher_relation", "student_course",
    "student_video_progress", "lead", "practice_session",
    "practice_question", "practice_answer", "learning_profile",
    "mastery_trend", "weak_point", "conversation_message",
}

def test_all_tables_registered():
    assert EXPECTED_TABLES <= set(Base.metadata.tables.keys())

def test_create_and_insert():
    from sqlalchemy.orm import Session
    from shared.infrastructure.db.models.business import Lead
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Lead(lead_id="l1", contact="13800000000", direction="AI"))
        s.commit()
        assert s.get(Lead, "l1").contact == "13800000000"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_db.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 `base.py`/`session.py`/模型**

模型列类型遵循技术设计 6.2（`content`/`reference_answer`/`video_ids`/`answer_content`/`profile_json` 用 SQLAlchemy `JSON`；`price`/`score`/`total_score` 用 `Numeric`；布尔用 `Boolean`；`created_at`/`synced_at`/`*_at` 用 `DateTime`，统一 `default=DateUtil.now` 或服务端默认）。主键用文档指定的业务主键（`varchar` 系列）或 `bigint` 自增。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_db.py -q`
Expected: PASS。

- [ ] **Step 5: 配置 Alembic 并生成初始迁移**

```bash
source .venv/Scripts/activate && alembic init alembic
```

编辑 `alembic/env.py`：导入 `Base` 与 `shared.infrastructure.db.models`，`target_metadata = Base.metadata`，从 `Settings().database_url` 取 URL。然后：

```bash
source .venv/Scripts/activate && alembic revision --autogenerate -m "initial schema"
source .venv/Scripts/activate && alembic upgrade head
```

Expected: 生成 `alembic/versions/0001_initial.py`（自动编号可能不同，以实际文件名为准）并成功建表，`data/app.db` 生成。

- [ ] **Step 6: Commit**

```bash
git add tests/infrastructure/test_db.py shared/infrastructure/db alembic.ini alembic && git commit -m "feat: add ORM models and alembic initial migration"
```

---

### Task 7: shared/infrastructure/memory 会话记忆（内存实现）

**Files:**
- Create: `shared/infrastructure/memory/port.py`、`shared/infrastructure/memory/in_memory.py`
- Test: `tests/infrastructure/test_memory.py`

**Interfaces:**
- Produces:
  - `MemoryPort(Protocol)`：`set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None`、`get(self, key: str, default: Any = None) -> Any`、`delete(self, key: str) -> None`
  - `InMemoryStore`：实现 `MemoryPort`，内部 `dict` + `time.monotonic()` 记录过期时间

- [ ] **Step 1: 写失败测试**

`tests/infrastructure/test_memory.py`：
```python
from shared.infrastructure.memory.in_memory import InMemoryStore

def test_set_get_delete():
    s = InMemoryStore()
    s.set("k", 1)
    assert s.get("k") == 1
    s.delete("k")
    assert s.get("k", default="d") == "d"

def test_ttl_expiry(monkeypatch):
    s = InMemoryStore()
    s.set("k", 1, ttl_seconds=10)
    assert s.get("k") == 1
    monkeypatch.setattr("shared.infrastructure.memory.in_memory.time.monotonic", lambda: 999999)
    assert s.get("k", default="expired") == "expired"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_memory.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 `InMemoryStore`**

存 `{key: (value, expire_at)}`，`expire_at = time.monotonic() + ttl_seconds`（`ttl_seconds` 为 `None` 则永不过期）；`get` 时过期则删除并返回 `default`。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_memory.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/infrastructure/test_memory.py shared/infrastructure/memory && git commit -m "feat: add in-memory conversation store"
```

---

### Task 8: shared/infrastructure/observability 日志与追踪

**Files:**
- Create: `shared/infrastructure/observability/logging.py`、`shared/infrastructure/observability/tracing.py`
- Test: `tests/infrastructure/test_observability.py`

**Interfaces:**
- Produces:
  - `configure_logging() -> None`（structlog 配置为 JSON 或 key=value）
  - `get_logger(name: str)`（structlog 包装）
  - `TraceIdMiddleware`（FastAPI `BaseHTTPMiddleware` 子类）：读请求头 `X-Trace-Id`，缺省则生成 uuid4 hex；`contextvars` 绑定；响应头写回 `X-Trace-Id`
  - `get_trace_id() -> str`

- [ ] **Step 1: 写失败测试**

`tests/infrastructure/test_observability.py`：
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.infrastructure.observability.tracing import TraceIdMiddleware

def test_trace_id_generated_and_echoed():
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    @app.get("/x")
    def x():
        return {"ok": True}
    c = TestClient(app)
    r1 = c.get("/x")
    assert r1.headers.get("x-trace-id")  # 无请求头时生成
    r2 = c.get("/x", headers={"X-Trace-Id": "abc123"})
    assert r2.headers.get("x-trace-id") == "abc123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_observability.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 logging 与 tracing**

`TraceIdMiddleware.dispatch` 中读取/生成 traceId，`contextvars.ContextVar` 存值，调用后写响应头。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_observability.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/infrastructure/test_observability.py shared/infrastructure/observability && git commit -m "feat: add structlog config and trace id middleware"
```

---

### Task 9: shared/infrastructure/tool_registry 工具注册

**Files:**
- Create: `shared/infrastructure/tool_registry/registry.py`
- Test: `tests/infrastructure/test_tool_registry.py`

**Interfaces:**
- Produces:
  - `ToolRegistry`：`register(self, context: str, name: str, fn: Callable) -> None`、`get(self, context: str, name: str) -> Callable`、`list(self, context: str | None = None) -> dict[str, dict[str, Callable]]`
  - 未注册时 `get` 抛 `KeyError`

- [ ] **Step 1: 写失败测试**

`tests/infrastructure/test_tool_registry.py`：
```python
import pytest
from shared.infrastructure.tool_registry.registry import ToolRegistry

def test_register_get_context_isolation():
    r = ToolRegistry()
    f1 = lambda: 1
    f2 = lambda: 2
    r.register("sales", "query_course", f1)
    r.register("teaching", "query_course", f2)
    assert r.get("sales", "query_course") is f1
    assert r.get("teaching", "query_course") is f2

def test_list_filtered_by_context():
    r = ToolRegistry()
    r.register("sales", "a", lambda: 1)
    r.register("teaching", "b", lambda: 2)
    assert set(r.list("sales").keys()) == {"a"}

def test_get_missing_raises():
    r = ToolRegistry()
    with pytest.raises(KeyError):
        r.get("sales", "nope")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_tool_registry.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 `ToolRegistry`**

内部 `dict[str, dict[str, Callable]]`，`list(None)` 返回全部上下文。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/infrastructure/test_tool_registry.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/infrastructure/test_tool_registry.py shared/infrastructure/tool_registry && git commit -m "feat: add context-isolated tool registry"
```

---

### Task 10: api 统一响应、异常处理与健康检查

**Files:**
- Create: `api/schemas.py`、`api/handlers.py`、`api/routes/health.py`、`api/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `ErrorCode`/`AppException`（Task 3）、`TraceIdMiddleware`（Task 8）
- Produces:
  - `ApiResponse(BaseModel, Generic[T])`：`code: int`、`message: str`、`data: T | None = None`、`traceId: str | None = None`
  - `ok(data=None, trace_id=None) -> ApiResponse`（`code=0, message="success"`）
  - `register_exception_handlers(app) -> None`：`AppException` → 以其 `http_status` 返回 `{code: e.code, message: e.message}`；`RequestValidationError` → 400；未捕获 `Exception` → 500（`ErrorCode.INTERNAL`，隐藏内部细节）
  - `create_app() -> FastAPI`：挂 `TraceIdMiddleware`、`register_exception_handlers`、include `health` router
  - `GET /health` → `{"code":0,...,"data":{"status":"ok"}}`；`GET /ready` → `{"code":0,...,"data":{"status":"ready"}}`

- [ ] **Step 1: 写失败测试**

`tests/test_api.py`：
```python
from fastapi.testclient import TestClient
from api.main import create_app

def test_health():
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0 and body["message"] == "success"
    assert body["data"]["status"] == "ok"
    assert body["traceId"]

def test_ready():
    r = TestClient(create_app()).get("/ready")
    assert r.status_code == 200 and r.json()["code"] == 0
```

`tests/test_api_errors.py`：
```python
from fastapi import APIRouter
from fastapi.testclient import TestClient
from api.main import create_app
from shared.common.exception.base import NotFoundError
import api.main as main_module

def test_app_exception_mapped():
    app = create_app()
    @app.get("/boom")
    def boom():
        raise NotFoundError("missing")
    r = TestClient(app).get("/boom")
    assert r.status_code == 404
    assert r.json()["code"] == 40400
```

- [ ] **Step 2: 运行测试确认失败**

Run: `source .venv/Scripts/activate && pytest tests/test_api.py tests/test_api_errors.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现 schemas/handlers/health/main**

`handlers.py` 用 FastAPI `app.exception_handler` 注册；`main.py` 暴露 `app = create_app()` 供 uvicorn 引用。

- [ ] **Step 4: 运行测试确认通过**

Run: `source .venv/Scripts/activate && pytest tests/test_api.py tests/test_api_errors.py -q`
Expected: PASS。

- [ ] **Step 5: 冒烟：启动服务验证**

```bash
source .venv/Scripts/activate && uvicorn api.main:app --port 8000
```

Expected: `curl http://127.0.0.1:8000/health` 返回 `code=0` 的 JSON。（验证后停止进程）

- [ ] **Step 6: Commit**

```bash
git add tests/test_api.py tests/test_api_errors.py api && git commit -m "feat: add fastapi app with unified response and health endpoints"
```

---

### Task 11: 依赖规则检查（import-linter）

**Files:**
- Create: `.importlinter`
- Test: 运行 `lint-imports` 作为验证（不新增 pytest）

**Interfaces:**
- Consumes: 全部包（Task 1–10）

- [ ] **Step 1: 写 `.importlinter` 合约**

`root_packages = ["shared", "contexts", "orchestrator", "api"]`；两条合约：
- `layers` 合约 `ddd-layers`：层级自底向上 `shared.common` → `shared.infrastructure` → `contexts` → `orchestrator` → `api`（禁止反向）
- `independence` 合约 `contexts-independent`：`modules = ["contexts.sales_assistant", "contexts.teaching_assistant", "contexts.course_assistant", "contexts.exam_paper_generation", "contexts.self_practice", "contexts.exam_grading", "contexts.learning_analytics"]`

- [ ] **Step 2: 运行检查**

```bash
source .venv/Scripts/activate && lint-imports
```

Expected: 通过（无违规输出，退出码 0）。若报配置语法问题，修正 `.importlinter` 直至通过。

- [ ] **Step 3: Commit**

```bash
git add .importlinter && git commit -m "chore: enforce DDD dependency rules with import-linter"
```

---

## 完成标准（阶段 0 验收）

- `pytest -q` 全绿（Task 2–10 的全部单测/接口测试）。
- `lint-imports` 通过。
- `alembic upgrade head` 成功建出 18 张表。
- `uvicorn api.main:app` 可启动，`/health` `/ready` 返回统一结构。
- git 历史含每个 Task 一次 commit。

# 营销 Agent（sales_assistant）设计

- 日期：2026-11-18
- 状态：待确认
- 上游：《需求规格说明书》8.1（FR-001~005）、《系统技术设计说明书》5.1/5.2/8.1、《分阶段实施设计》阶段 2

## 1. 意图与背景

落地售前咨询 Agent：多轮对话识别学员学习方向/岗位 → 推荐课程 → 回答报名/学习 FAQ → 收集线索留资。面向游客/潜在学员，7×24 在线，把咨询流量转化为可跟进的销售线索（lead）。

## 2. 目标 / 非目标 / 反目标

**目标**
- FR-001 方向引导与岗位识别（多轮追问、模糊澄清、AI 细分岗位）。
- FR-002 课程介绍咨询（方向/岗位 → 课程 → LLM 话术）。
- FR-003 报名就业咨询（确定性 FAQ）。
- FR-004 学习咨询（确定性 FAQ）。
- FR-005 线索留资（写 lead 表 + report_vip 端口）。
- `POST /api/v1/sales/chat` 端点。

**非目标（本阶段不做）**
- 不引 LangGraph（已定：纯 Service）。
- 不引向量库/RAG（Milvus 属阶段 3）。
- 不做 report_vip 真实外部调用（端口 + stub）。
- 不做鉴权（v1.0 无 auth 层）。

**反目标（做了即算失败）**
- 破坏 DDD 依赖规则（sales_assistant 只依赖 shared + 自身，不 import 其他 context）。
- LLM 输出无确定性兜底（方向/岗位必须经确定性枚举校验）。
- 无匹配课程时编造课程（必须确定性规则「如实告知 + 引导留资」）。

## 3. 约束

- 沿用阶段 0/1 已落地：Python 3.11+、FastAPI、SQLAlchemy 2.x、Pydantic v2、structlog。
- LLM 走 `shared.infrastructure.llm.LLMPort`（纯文本 chat，返回 `LLMResult.content`）；结构化输出用 prompt + `json.loads` 解析（同阶段 1 批改）。
- 会话记忆走 `shared.infrastructure.memory.MemoryPort`（内存实现）。
- 复用阶段 0 已建表：`Lead`、`CourseCategory`、`Course`、`ConversationMessage`——本阶段**不新增表**。

## 4. 关键决策（approaches）

| 决策点 | 候选 | 选定 | 理由 |
|--------|------|------|------|
| 编排方式 | ① LangGraph ② 纯 Service + 端口 | **② 纯 Service + 端口** | 用户确认；与阶段 1 一致；`LLMPort` 纯文本无工具调用，LangGraph 只提供状态机、价值有限 |
| FAQ 知识来源 | ① 内置确定性 FAQ ② 纯 LLM ③ 暂缓 | **① 内置确定性 FAQ** | 用户确认；符合「确定性/LLM 分工」，无向量库也能诚实作答 |

## 5. 架构

### 5.1 目录结构（沿用阶段 1 分层）

```
contexts/sales_assistant/
  domain/
    directions.py   # 方向/岗位枚举 + 归一化校验 + FAQ 表（纯函数）
    ports.py        # VipReportPort Protocol
  application/
    service.py      # SalesChatService（编排）
  infrastructure/
    repository.py   # CourseRepository / LeadRepository
api/
  schemas/sales.py  # SalesChatRequest
  routes/sales.py   # POST /api/v1/sales/chat
  dependencies.py   # + get_sales_chat_service
api/main.py         # + include sales_router
tests/contexts/sales_assistant/test_directions.py
tests/contexts/sales_assistant/test_service.py
tests/test_sales_api.py
```

### 5.2 确定性 / LLM 分工

| 环节 | 实现 |
|------|------|
| 方向/岗位枚举 | 确定性（`directions.py` 枚举 + normalize 校验） |
| 意图识别 | LLM 输出 JSON `{intent, direction, position}`，再经确定性枚举校验兜底 |
| 课程查询 | 确定性（`CourseCategory`/`Course` 表查询） |
| 课程话术 | LLM 组织（输入课程数据） |
| FAQ 命中 | 确定性直接答；未命中 → LLM 兜底 |
| 无匹配课程 | 确定性规则「如实告知 + 引导留资」 |
| 留资 | 确定性写 lead + report_vip 端口（stub） |

**方向/岗位枚举**（FR-001）：方向 = `Java / 前端 / AI / 其他`；AI 方向岗位 = `大模型算法岗 / 大模型应用开发岗`；「我也没方向」→ 引导找老师。`normalize_direction`/`normalize_position` 把 LLM 自由文本（含别名）归一化到上述枚举，未知值归 `其他`/`None`。

### 5.3 数据流（chat）

```
用户消息
 → 取会话记忆（conversation_id → {direction, position}）
 → 意图识别（LLM → {intent, direction, position}，枚举校验）
 → 条件分支：
    方向未明 → 追问（返回引导话术，记忆已选方向/岗位）
    课程介绍 → 方向/岗位 → 查课程 → LLM 话术（无匹配 → 如实告知 + 引导留资）
    报名就业/学习咨询 → FAQ 命中直接答 / 未命中 LLM 兜底
    留资 → 提取 contact/方向/岗位/备注 → 写 lead + report_vip
 → 更新会话记忆，返回 {reply, direction, position, courses, leadSaved}
```

## 6. API 契约

`POST /api/v1/sales/chat`（统一响应 `{code, message, data, traceId}`）

**请求**：
```json
{"conversationId": "c_xxx（可空，首次由服务端生成）", "message": "想学编程", "source": "web"}
```

**响应 data**：
```json
{
  "conversationId": "c_xxx",
  "reply": "...",
  "direction": "AI",
  "position": "大模型算法岗",
  "courses": [{"courseId": "c1", "name": "…", "price": 0, "durationHours": 0, "highlights": "…"}],
  "leadSaved": false
}
```

- `direction`/`position`：本次识别或记忆中的方向/岗位，未定则 `null`。
- `courses`：仅课程介绍分支非空。
- `leadSaved`：本次是否成功留资。

## 7. 留给实施者的自由度

- 意图识别 prompt 与 JSON schema 细节（intent 取值集合、字段名）。
- FAQ 具体条目内容（报名流程、是否包就业、学习周期、能否自学等）。
- 方向/岗位 → 课程分类树的映射算法细节（如何用 `Course.direction`/`position` 与 `category_id` 组合查询）。
- 会话记忆的 TTL、key 命名；`ConversationMessage` 持久化留作后续（线索是 v1.0 的持久化产物）。
- 文件内模块切分粒度。

## 8. 补充决策（构建者核查后确定）

以下决策在构建者核查后由设计者代定，实施者按此实现，交付时人工可复核。

1. **联系方式获取（用户拍板）**：留资分支由 LLM 从当前消息自由文本提取 `contact`（电话/微信/QQ/邮箱）与 `remark`。请求 schema 不变（无 `contact` 字段）。未提取到 → 回复引导用户留下联系方式，`leadSaved=false`，不写 lead；用户随后在对话中给出联系方式时（再次判为留资意图），提取并写 lead。
2. **方向未知留资**：`direction` 未知时写入已定义枚举 `"其他"`（`normalize_direction` 的兜底值，非编造方向）；`position` 未知则存 `None`。
3. **VipReportPort 契约**：`VipReportPort.report_vip(lead: Lead) -> bool`，stub 恒返回 `True`。`leadSaved` 仅反映 lead 行写入成功（`report_vip` 尽力而为；stub 失败不回滚、置 `vip_reported=False`）。
4. **意图识别上下文与优先级**：意图识别 LLM 收到 `[system, 当前消息]` + 记忆上下文字段（`已识别方向: X / 岗位: Y`，仅在有值时附上）。记忆（已确认的方向/岗位）优先，LLM 本次推断仅在记忆缺该字段时补空。LLM JSON 解析失败（重试一次后）→ 兜底走「方向未明 → 追问」分支。

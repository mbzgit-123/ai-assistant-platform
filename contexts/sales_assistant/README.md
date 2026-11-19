# sales_assistant（智能营销 / 智能客服）

面向**售前获客**场景的营销 Agent：识别用户学习意向（方向/岗位）、推荐课程、回答 FAQ、并在适当时机留取线索（联系方式）。

## 职责

- 意图识别：将用户消息归为 `direction_guide | course_intro | enrollment_faq | study_faq | lead_capture` 五类之一
- 方向/岗位归一化：把口语化描述映射到 `Java / 前端 / AI` 与 AI 下的两个岗位
- 课程推荐：按方向+岗位查课程，用 LLM 组织推荐话术
- FAQ 咨询：报名/学习两类 FAQ 走确定性关键词匹配，未命中回退 LLM
- 线索留资：从消息中抽取联系方式，落库 `Lead` 并上报 VIP 线索

## 分层结构

```
contexts/sales_assistant/
├── domain/
│   ├── directions.py   # 方向/岗位归一化 + FAQ 关键词表
│   └── ports.py        # VipReportPort（VIP 线索上报端口）
├── application/
│   └── service.py      # SalesChatService（会话编排）
├── infrastructure/
│   ├── repository.py   # SalesRepository（课程查询 / 线索落库）
│   └── vip_report.py   # VipReportPort 适配器
└── interface/
    ├── routes.py       # REST 路由
    ├── schemas.py      # 请求模型
    └── dependencies.py # 依赖装配
```

## 端口

- **定义（对外提供）**：`VipReportPort.report_vip(lead) -> bool`
- **消费（依赖）**：`LLMPort`、`MemoryPort`

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/sales/chat` | 营销会话入口，返回回复 + 识别出的方向/岗位/课程/是否已留资 |

## 依赖

- 仅依赖 `shared`（LLM、Memory、DB 模型、统一响应）
- 与其他 context 无依赖（`contexts-leaf-independent` 契约）

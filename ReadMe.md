# 实现过程
## 1.命令实现
         理解 docs 下的需求文档和技术文档 帮我实现这个项目  而且是分阶段实现  每个阶段实现了后 我确定了 再往下实现。

## 2.运行测试

### 环境要求

- 测试环境使用 conda `myenv`（Python 3.10，路径 `E:\anaconda3\envs\myenv`）。
- 项目自带的 `.venv`（Python 3.13）**不含** RAG 重依赖（torch / Milvus / sentence-transformers），真实集成测试会在其中被自动跳过。

### 运行步骤

在项目根目录执行（`pytest` 的 `testpaths=["tests"]` 与数据库相对路径都依赖项目根目录）：

```bash
cd D:\projects\项目阶段\ai-assistant-platform
```

方式 A（先激活 myenv）：

```bash
conda activate myenv
python -m pytest -q
```

方式 B（直接用完整路径，不激活）：

```bash
E:\anaconda3\envs\myenv\python.exe -m pytest -q
```

### 常用命令

| 目的 | 命令 |
|------|------|
| 全量测试 | `python -m pytest -q` |
| 详细输出 | `python -m pytest -v` |
| 只跑销售助手 | `python -m pytest tests/contexts/sales_assistant/ -q` |
| 只跑服务层测试 | `python -m pytest tests/contexts/sales_assistant/test_sales_service.py -v` |
| 只跑真实集成测试（BGE-M3 + Milvus） | `python -m pytest tests/contexts/sales_assistant/test_knowledge_base_integration.py -v` |
| 跳过集成测试（快速跑） | `python -m pytest -q --ignore=tests/contexts/sales_assistant/test_knowledge_base_integration.py` |

### 预期结果

- 全量：**198 passed**（197 单元测试 + 1 真实集成测试）。
- 真实集成测试会加载 BGE-M3 模型（首次约 10~15 秒）。
- 若出现 `DeprecationWarning: ranker_type/ranker_params is deprecated`，这是 langchain-milvus 0.4.0 的弃用告警，不影响结果，可忽略。

## 3.启动服务 + Swagger 测试

### 启动

在项目根目录、conda `myenv` 环境下：

```bash
cd D:\projects\项目阶段\ai-assistant-platform
conda activate myenv
python -m uvicorn api.main:app --reload --port 8000
```

（`--reload` 可选，改代码自动重启；纯测试可去掉。）

### Swagger

浏览器访问：

```
http://127.0.0.1:8000/docs
```

### 测试 sales 接口

Swagger 里找到 **POST `/api/v1/sales/chat`** → **Try it out** → 填 body：

```json
{
  "conversationId": null,
  "message": "报名流程是怎样的？",
  "source": "web"
}
```

返回体 `data` 字段：`reply`（回复）、`direction`、`position`、`courses`、`leadSaved`、`sources`（FAQ 溯源）。

### 两个前提

1. **不配 LLM 只能测接口通断**：默认 `llm_provider=fake`（无 `.env` 时），fake LLM 无法识别意图，`chat` 只会返回方向引导话术，走不到 FAQ 检索分支。要真正测 FAQ，需在项目根新建 `.env`：

   ```env
   LLM_PROVIDER=deepseek
   DEEPSEEK_API_KEY=你的key
   DEEPSEEK_BASE_URL=https://api.deepseek.com
   DEEPSEEK_MODEL=deepseek-chat
   ```

   改完 `.env` 后重启 uvicorn（`--reload` 对 `.env` 不一定触发，手动重启最稳）。

2. **测 FAQ 前先建知识库**：

   ```bash
   python -m contexts.sales_assistant.infrastructure.build_knowledge_base
   ```

   把 `contexts/sales_assistant/data/faq.md` 写入 `data/milvus_sales_faq.db`。不建库时 FAQ 分支会降级返回「抱歉…转顾问老师」兜底话术（不报错，只是没有语义答案）。

### 快速验证顺序

1. 先只启动服务，测 `GET /health` → 确认服务起来。
2. 建库 → 配 `.env` → 重启 → 测 `POST /api/v1/sales/chat`，message 填 FAQ 问题（如「报名流程是怎样的？」），看 `data.sources` 是否有内容。


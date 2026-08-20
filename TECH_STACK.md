# 技术栈

本文档记录已经确定的技术选型和仍需决策的项目。新增核心依赖前，应先更新本文件并说明替代方案和取舍。

## 后端

| 领域 | 技术 | 用途 |
|---|---|---|
| 语言 | Python 3.12 | 采集、AI、Telegram、知识库和 API |
| Web API | FastAPI + Uvicorn | 前端 API、管理接口和健康检查 |
| 数据模型 | Pydantic v2 | 配置、领域 DTO 和 AI 结构化输出校验 |
| 数据库 | SQLite + WAL | 运行状态、去重、投递、重试和搜索索引 |
| 数据访问 | SQLAlchemy 2 | Repository 实现和事务边界 |
| 数据迁移 | Alembic | 数据库 Schema 版本管理 |
| HTTP | httpx | 外部 API 和内容请求 |
| RSS/Atom | feedparser | Feed 解析 |
| 调度 | APScheduler | 自动轮询和周期任务 |
| Telegram | python-telegram-bot | 频道推送、按钮和回调 |
| 模板 | Jinja2 | 可版本化的 Telegram 消息模板 |
| 配置 | pydantic-settings + YAML | 环境变量、来源和运行配置 |
| 日志 | structlog JSON | 结构化日志和运行诊断 |

## AI 与 Prompt

第一阶段 LLM 供应商确定为 DeepSeek。

```text
LLMPort
  └── OpenAICompatibleDeepSeekAdapter

PromptProvider
  ├── LocalPromptProvider
  └── LangfusePromptProvider
```

约束：

- 使用 DeepSeek 的 OpenAI-compatible API 接口。
- `base_url`、模型名、超时和重试策略通过配置提供。
- API Key 只存放在环境变量中。
- 模型输出必须通过 Pydantic Schema 校验。
- Langfuse Cloud 用于 Prompt 版本、Trace、成本和评测。
- GitHub 运行仓库保留稳定 Prompt fallback。
- 第一阶段不引入 LangChain、LlamaIndex 或通用 Agent 框架。

具体 DeepSeek 模型暂不在架构层写死，由运行配置和后续评测决定。

## 知识库与搜索

| 领域 | 技术 |
|---|---|
| 权威存储 | GitHub 私有 Markdown 仓库 |
| 元数据 | YAML front matter |
| 写入 | GitHub REST API |
| 全文搜索 | SQLite FTS5 派生索引 |
| 版本与恢复 | Git 历史 |

第一版不使用向量数据库。语义搜索以后通过 `SearchIndex` Port 增加，不修改知识库事实模型。

## 前端

| 领域 | 技术 |
|---|---|
| 语言 | TypeScript |
| UI | React |
| 构建 | Vite |
| 路由 | React Router |
| 服务端状态 | TanStack Query |
| 样式与组件 | Tailwind CSS + shadcn/ui |
| 图标 | Lucide |

前端采用双区结构：

```text
公开只读区
  情报、知识库、搜索、允许公开的提示词

私有管理区
  来源、模板、Prompt、上传、删除归档和运行管理
```

公开页面不直接访问 GitHub 或 SQLite，只通过 FastAPI 的只读 API 获取已发布内容。

知识条目默认私有且处于草稿状态。公开索引只收录同时满足 `visibility: public` 和 `publication_status: published` 的内容，避免把个人上传资料或未审核情报意外公开。

## 工程与部署

| 领域 | 技术 |
|---|---|
| Python 依赖 | uv + pyproject.toml + lockfile |
| 测试 | pytest + pytest-asyncio + respx + coverage |
| 格式与检查 | Ruff |
| 类型检查 | Pyright |
| CI | GitHub Actions |
| 服务管理 | systemd |
| HTTPS 与反向代理 | Caddy |

服务器初期运行：

```text
ai-intel-worker.service
ai-intel-api.service
```

第一阶段不使用 Docker、PostgreSQL、Redis、Celery、Kafka 或 Kubernetes。

## 当前纵向切片的实现状态

为了先验证完整业务链路，当前 `app/` 切片暂时使用 Python 标准库实现：

```text
sqlite3 + WAL       SQLite Repository 的第一版实现
urllib.request      外部 HTTP 调用的第一版实现
显式 Worker 调度    以来源轮询间隔驱动采集，并调度幂等的日报/周报
```

这些实现都位于适配器或基础设施边界内，Domain 和 Application 不依赖具体库。正式服务器部署前再引入 SQLAlchemy/Alembic、httpx 和调度库，并为替换增加集成测试；不会把临时代码散落到业务层。

## 尚未确定

### X 接入

需要在实现前比较：

- X 官方 API
- 合规的第三方数据服务
- 受控浏览器采集

决策时必须评估成本、稳定性、速率限制、登录态和平台条款。当前不选择具体实现。

### 管理区认证

公开只读模式已经确定，管理区具体认证方式在前端阶段确定。无论选择哪种方案，所有写接口都必须默认拒绝未认证访问。

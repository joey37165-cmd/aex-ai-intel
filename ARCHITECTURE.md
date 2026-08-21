# Aex AI 情报系统架构

本文档描述当前已经运行的模块边界，以及后续知识库功能应如何接入。项目采用模块化单体：一个 Worker、一个管理 API 和一个 SQLite 运行库，不提前拆分微服务。

## 1. 系统边界

当前系统分为三个已运行的子系统和一个规划中的子系统：

```text
已运行：情报采集与推送、日报/周报、模板管理
规划中：知识库与知识搜索
```

服务器上的 SQLite 只保存运行状态、消息去重、分析结果、投递记录、报告状态和模板版本。知识库 Markdown 的权威版本属于独立的 GitHub 仓库，不作为服务器正式数据保存。

## 2. 主数据流

```text
来源配置
   -> SourceAdapter.fetch()
   -> ContentItem
   -> 技术去重与运行状态记录
   -> Analyzer（DeepSeek）
   -> NotificationPolicy（S/A 且置信度 >= 0.75）
   -> 语义去重
   -> Delivery Queue
   -> Telegram 模板渲染
   -> Telegram
```

每个来源只负责把外部数据转换成统一的 `ContentItem`。AI 分析、发布门槛、语义去重和 Telegram 投递只有一套流程，不能按来源复制。

## 3. 模块划分

### 3.1 来源采集模块

来源配置位于 `config/sources.json`，适配器位于 `app/adapters/sources/`。当前适配器按外部协议或页面结构划分：

```text
RSS / Atom       rss.py
Sitemap          sitemap.py（可对新文章做一次内容补充）
Changelog        changelog.py / openai_changelog.py / gemini_changelog.py
IMAP Email       email.py
X                x.py（当前官方 X API 默认关闭）
```

通过 `xgo.ing` 接入的 X 账号属于 RSS 来源，不是 X 官方 API。GitHub Release 等 Feed 也复用 RSS 适配器；只有页面结构不同，才需要新增适配器。

`registry.py` 是来源类型到适配器的注册表。Worker 只调用注册表，不维护来源类型的 `if/elif` 分支。

统一接口：

```python
SourceAdapter.fetch(source_config) -> Iterable[ContentItem]
```

### 3.2 内容处理模块

领域模型位于 `app/domain/models.py`。内容处理包含两种不同的去重：

```text
技术去重：同一来源、同一外部 ID / URL / 内容指纹不重复处理
语义去重：不同来源报道同一事件时，只保留一个 Telegram 主通知
```

技术去重在来源适配器生成稳定 `item_id` 时完成；语义去重位于 `app/domain/deduplication.py`，由应用流程在 AI 分析后、投递前调用。

消息状态主要为：

```text
discovered -> notify -> queued -> sent
                         |
                         +-> ignore / review / retry
```

### 3.3 AI 分析模块

应用流程只依赖分析器接口，不依赖 DeepSeek SDK：

```text
Analyzer
  -> DeepSeek OpenAI-compatible Adapter
  -> Langfuse Prompt Provider
  -> 本地 Prompt fallback
```

AI 负责分类、标题翻译、摘要、重点、优先级和置信度。程序负责结构化输出校验和发布门槛，模型不能直接写入数据库或执行工具。

### 3.4 Telegram 投递模块

`app/application/pipeline.py` 负责投递流程，`app/adapters/telegram/` 负责 Telegram 网络边界：

```text
Delivery Queue -> TemplateProvider -> Telegram Notifier
```

实时情报使用 `realtime` 模板；日报和周报共用 `digest` 模板。发送失败会进入 SQLite 重试状态，进程重启后可以继续投递。

### 3.5 日报/周报模块

日报和周报是同一个报告模块的两种时间窗口：

```text
报告窗口计算
  -> 查询 notify 且符合发布门槛的内容
  -> URL 去重和数量限制
  -> DeepSeek 摘要
  -> digest 模板渲染
  -> Telegram 投递
```

报告状态使用稳定 `report_id` 保存，日报和周报不复制两套业务流程。

### 3.6 模板管理模块

管理 API 和前端只负责模板的控制面：

```text
草稿 -> 校验 -> 发布版本 -> Worker 读取
```

管理接口由 `ADMIN_API_TOKEN` 保护。Worker 只读取已发布模板；数据库不可用时回退到 `config/templates/`。

### 3.7 运行状态模块

`app/infrastructure/store.py` 是当前 SQLite 实现，保存：

```text
items、analyses、deliveries、job_runs、source_state、reports、message_templates
```

当前先保留一个 Store 门面。只有当知识库或并发需求增加后，才按 `ItemRepository`、`DeliveryRepository`、`ReportRepository`、`TemplateRepository` 拆分内部职责，不拆分数据库。

### 3.8 知识库模块（规划中）

知识库不进入实时推送主流程，未来通过 Telegram 决策进入独立服务：

```text
Telegram 回调
  -> KnowledgeService
  -> GitHub Knowledge Repository
  -> Markdown + YAML front matter
  -> 可重建的 SQLite 搜索索引
```

GitHub 是知识内容唯一事实来源，SQLite 搜索索引只是派生缓存。

## 4. 依赖方向

```text
Domain（纯规则和数据）
        ^
Application（业务流程）
        ^
Ports（外部能力接口）
        ^
Adapters / Infrastructure（具体实现）
```

`app/worker.py` 和 `app/api.py` 是组合根，负责创建具体适配器并注入应用流程。Domain 不得导入 SQLite、Telegram、DeepSeek 或 FastAPI。

## 5. 入口与部署

```text
ai-intel-worker.service
  python -m app.worker --daemon

ai-intel-api.service
  uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Worker 负责自动采集、AI 分析、实时推送和报告；API 负责模板管理。两者共享运行数据库，但进程职责分离。

## 6. 当前不做的拆分

- 不按每个 RSS 来源建立独立业务模块。
- 不把每个 AI 公司做成一个独立 Worker。
- 不引入微服务、消息队列、Redis、PostgreSQL 或容器编排。
- 不在知识库功能完成前提前引入 GitHub Repository 实现。

后续只有在出现明确的并发、事务、部署或测试需求时，才继续拆分 Store 或应用服务。

# Aex AI 情报与知识系统

这是一个面向个人 AI 情报输入、筛选、推送和知识沉淀的系统。

当前目标是把来自 RSS、Email、X 和 GitHub 的信息，经过 AI 筛选和固定模板格式化后推送到 Telegram；用户再从 Telegram 中选择值得长期保存的内容，写入 GitHub Markdown 知识库。

## 当前状态

- 40 个 RSS/Atom 已接入并启用，其中包含 15 个通过 `xgo.ing` 转换的 X 账号 RSS；另有 4 个 Sitemap、3 个 Changelog 和 1 个 Email 来源。
- Anthropic News 已通过官方 Sitemap 接入；Sitemap 只发现 URL，仅对新文章抓取一次标题和摘要。
- DeepSeek Official News 与 API Change Log 已接入；Change Log 按日期、标题和内容指纹拆分去重。
- Claude Platform Release Notes、OpenAI Developer Changelog 和 Mistral AI News 已接入。
- RSS → 去重 → Telegram 频道的最小 MVP 已验证成功。
- 首次基线已建立，不会重复推送历史消息。
- Telegram 频道已接通，Worker 可通过 `python -m app.worker --daemon` 持续运行。
- Newsletter 已接入 TLDR AI Email、The Rundown AI RSS、The Neuron Atom、The Batch Sitemap 和 Superhuman AI Sitemap；Product Hunt AI 产品 Feed、GitHub Release 来源和 Gemini API Changelog 也已接入。X 官方 API Adapter 仍默认关闭，当前使用 15 个 `xgo.ing` 第三方 RSS 账号源；知识库按钮尚未实现，私有模板管理界面已接入管理 API。
- 第一阶段 LLM 供应商已确定为 DeepSeek；具体模型通过配置选择，不写死在业务代码中。
- 第一阶段正式 Worker 已建立：`python -m app.worker --daemon`，生产环境由 `systemd` 托管。
- 日报和周报已接入同一个常驻 Worker：日报每天 09:00 汇总前一天 09:00 至当天 09:00，周报每周一 09:00 汇总上周一 09:00 至本周一 09:00，时区均为 `Asia/Shanghai`。
- 未来前端采用公开只读页面与私有管理页面分离的模式。

### 模板管理界面

模板管理界面位于 `web/`，当前只管理两套 Telegram 模板：日常情报，以及日报/周报共用模板。页面通过带 Bearer Token 认证的 FastAPI 管理接口读写 SQLite 模板版本，不读取或保存 Telegram Bot Token、Chat ID、模型密钥等配置。

模板状态分为草稿与已发布版本：保存草稿不会影响 Worker，点击发布后才会生成不可变的新版本。Worker 在每次渲染消息时读取当前发布版本；数据库模板不可用时自动回退到 `config/templates/` 中的仓库模板。

启动界面：

```powershell
cd web
npm install
npm run dev
```

另开一个终端启动管理 API：

```powershell
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

打开 `http://localhost:5173/` 并输入 `.env` 中的 `ADMIN_API_TOKEN`，可以切换模板、编辑 HTML、点击变量插入、预览 Telegram 效果、保存草稿、发布版本和恢复历史版本。

生成管理 Token：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

将结果只写入本地或服务器 `.env` 的 `ADMIN_API_TOKEN`，不要提交到 GitHub。管理 Token 只保存在当前浏览器的 `sessionStorage`，关闭标签后清除。

也可以让程序直接生成并安全写入 `.env`，命令只显示 Token 指纹，不显示完整凭据：

```powershell
python -m app.admin_token --env .env
```

验证命令：

```powershell
python -m unittest discover -s tests -v
python telegram_poc.py preview
python telegram_poc.py bootstrap
python telegram_poc.py run
python -m app.worker --db data/test-runtime.db --bootstrap
python -m app.worker --db data/test-runtime.db --dry-run
python -m app.worker --db data/runtime.db --status
python -m app.worker --db data/runtime.db --prompt-status
python -m app.worker --db data/runtime.db --preview-template
python -m app.worker --db data/runtime.db --preview-digest
python -m app.worker --db data/runtime.db --reports-once
```

## 总体架构

```text
RSS / Sitemap / Email / X / GitHub
          |
          v
      消息采集层
          |
          v
    标准化、去重、状态记录
          |
          v
      AI 筛选与结构化提取
          |
          v
      固定 Telegram 模板渲染
          |
          v
       Telegram 频道
          |
    加入 / 稍后 / 忽略
          |
          v
       GitHub API
          |
          v
    GitHub Markdown 知识库
          |
          v
      可重建搜索索引
          |
          v
          前端
```

## 核心边界

### 服务器

服务器只负责运行系统：

- 按每个来源的配置频率自动采集消息
- AI 筛选和摘要
- Telegram 推送
- 接收 Telegram 决策
- 通过 GitHub API 写入知识库
- 保存 SQLite 运行状态、日志、重试队列和搜索索引

服务器不作为知识库的权威存储，不保存知识库的正式 Markdown 副本。

### GitHub

建议使用两个私有仓库：

1. `ai-intel-runtime`：程序代码、配置、测试和部署文件。
2. `ai-knowledge-base`：长期知识库 Markdown、索引和归档内容。

知识库仓库是知识内容的唯一事实来源。服务器上的搜索索引只是可删除、可重建的派生缓存。

### Telegram

Telegram 是阅读、通知和人工决策入口，不是知识库。推送消息可以带有：

```text
[加入知识库] [稍后处理] [忽略]
```

## AI 处理原则

AI 先输出结构化 JSON，程序再使用固定模板渲染 Telegram 消息。不要让模型直接生成最终 HTML 或 Markdown 消息。

推荐的结构化字段：

```json
{
  "display_title": "中文消息标题",
  "summary": "一句话摘要",
  "why_it_matters": "为什么值得关注",
  "category": "AI 前沿信息",
  "priority": "S",
  "action": "值得测试",
  "confidence": 0.92,
  "event": {
    "event_type": "model_release",
    "organization": "DeepSeek",
    "product": "V4",
    "version": "V4",
    "core_claim": "发布新模型并更新 API",
    "event_time": "2026-08-21"
  }
}
```

消息模板属于产品展示逻辑，存放在运行仓库并支持版本化。AI Prompt 属于模型运行逻辑，计划接入 Langfuse 做版本、追踪和评测；运行仓库保留稳定 Prompt 作为 fallback。

当前本地版本文件为 `config/templates/telegram.html`（实时情报）和 `config/templates/telegram_digest.html`（日报/周报共用），以及 `config/prompts/intelligence_filter.md`。实时消息会使用 AI 生成的 `display_title`，统一为中文并移除标题表情；`{category_icon}` 在 AI 前沿标题前显示 `📝`，在 AI 应用标题前显示 `📌`；链接行显示 `↗ 阅读原文` 和 `𝕏 Aex0x0`。修改模板和 Prompt 不需要改业务流程代码。

日报和周报共用同一个摘要模板，报告类型和周期由数据注入：

```text
日报：每天 09:00（Asia/Shanghai）
周报：每周一 09:00（Asia/Shanghai）
```

时间配置记录在 `config/reports.json`。日报与周报使用同一套自动流程：

```text
到期窗口计算
  -> 查询窗口内 AI 最终判定为 notify 的 S/A 内容
  -> 按 URL 去重并限制候选数量
  -> DeepSeek 生成结构化摘要
  -> 程序使用 telegram_digest.html 渲染
  -> Telegram 发送
  -> SQLite 记录 report_id、Prompt 版本、message_id 和重试状态
```

报告使用稳定的 `report_id` 保证同一周期不会重复创建。发送或模型调用失败会持久化并采用有上限的指数退避；服务器在计划时间后 24 小时内恢复时会补发，超过补发窗口不会发送陈旧周报。`--reports-once` 用于立即处理当前到期报告，生产环境不依赖手工执行该命令。

报告摘要使用独立 Prompt。仓库 fallback 位于 `config/prompts/digest_summary.md` 和 `config/prompts/digest_summary_user.md`；Langfuse Prompt 名默认为 `ai-intelligence-digest`，可通过 `LANGFUSE_DIGEST_PROMPT_NAME` 与 `LANGFUSE_DIGEST_PROMPT_LABEL` 修改。Langfuse 中尚未创建该 Prompt 或暂时不可用时，系统继续使用本地 fallback。

Telegram 发布门槛位于 `config/publishing.json`。DeepSeek 只输出 `notify` 或 `ignore`，程序再执行确定性门槛；S、A、B 级的高价值信息都可以推送，低于 `0.75` 置信度或不符合输出契约的结果会安全降为 `ignore`。优先级只表达重要程度，不再决定信息是否能够推送。

跨来源去重采用两阶段流程：第一轮筛选同时抽取 `event` 特征；本地标题和摘要规则只负责寻找 72 小时内的疑似候选，不直接认定重复。命中候选后，第二个去重 Prompt 才会调用 DeepSeek，输出 `duplicate`、`update` 或 `independent`。只有 `duplicate` 且置信度达到 `DEDUP_MIN_CONFIDENCE`（默认 `0.80`）才会抑制推送；`update`、`independent`、低置信度或调用失败均会放行。每次审查写入 SQLite 的 `dedup_reviews`，便于追踪模型、Prompt 版本和判断理由。

```json
{
  "telegram": {
    "allowed_priorities": ["S", "A", "B"],
    "min_confidence": 0.75
  }
}
```

修改 Prompt 后同步更新 `.env` 中的 `PROMPT_VERSION`，便于后续比较不同版本的筛选效果。`--status` 会显示分析决策与优先级分布，用于观察规则是否过松或过严。

情报筛选不再使用无法自动闭环的 `review` 状态。正文抓取或外部调用失败属于技术故障，不得作为内容决策；后续应由独立的有上限重试状态处理。历史 `review` 记录在打开数据库时迁移为 `ignore`，不会补发旧消息，原始分析数据仍保留用于审计。

第一阶段通过 OpenAI-compatible 适配器调用 DeepSeek API。API 地址、模型名和密钥全部通过配置注入，Domain 和 Application 层不得依赖 DeepSeek SDK 或具体模型名称。

## 知识库分类

知识库统一使用 Markdown + YAML front matter，按来源区分手动资料和情报资料：

```yaml
origin: manual
```

或：

```yaml
origin: intelligence
```

三大领域：

```text
models    大模型、模型更新、能力和评测
context   系统提示词、对话、上下文工程和记忆
tools     软件、API、插件、Agent 和工作流工具
```

提示词是知识库中的一等内容，至少需要记录：适用模型、变量、输入输出示例、版本、评测结果和适用场景。

所有知识条目还需要记录可见性和发布状态，默认值为：

```yaml
visibility: private
publication_status: draft
```

过期内容采用：

```text
active -> review -> archive
```

从当前知识库移除，但保留 Git 历史，避免误删后无法恢复。

## 目标代码结构

正式版本采用模块化单体，不一开始拆成微服务：

```text
app/
  domain/
  application/
  ports/
  adapters/
    sources/
    telegram/
    github/
    langfuse/
  infrastructure/
  api/
  worker/
```

关键接口包括：

- `SourceAdapter`：RSS、Email、X、GitHub 等来源适配器。
- `NotificationPort`：Telegram 推送和按钮事件。
- `KnowledgeRepository`：通过 GitHub API 读写知识库。
- `StateStore`：SQLite 状态、去重、发送记录和重试。

## 前端访问边界

未来前端分为两个区域：

```text
公开只读页面
  情报流、知识库浏览、全文搜索、提示词公开内容

私有管理页面
  消息源管理、模板和 Prompt 管理、资料上传、归档删除、运行状态
```

所有写操作和系统配置必须经过身份认证。只有明确标记为 `public + published` 的内容才能由公开 API 返回。公开页面不能暴露原始邮件、未审核情报、内部 Prompt、运行日志或任何密钥。

## 重要工程约束

- 每个消息必须可以通过 URL 或内容指纹幂等识别。
- Telegram 重复点击不能生成重复知识卡片。
- GitHub API 写入需要处理超时、限流和冲突重试。
- 程序重启后必须能够从 SQLite 状态继续工作。
- 正式环境必须由 `systemd` 管理常驻 Worker，不能依赖人工执行命令或 PowerShell 循环。
- 自动轮询必须支持单来源超时隔离、失败重试和优雅退出；一个来源失败不能阻塞其他来源。
- 所有外部输入都视为不可信内容，不能让消息内容覆盖系统 Prompt。
- Token、Cookie、API Key 只能放在服务器环境变量或 `.env`，不能写入 Git。
- 正式功能必须有单元测试和失败路径测试。

## 分期计划

1. 完成来源注册、自动采集、去重、AI 结构化筛选、模板渲染、Telegram 自动推送、重试和运行监控。
2. 加入 Telegram 决策按钮和 GitHub 知识库写入。
3. 加入手动上传、过期治理和可重建搜索索引。
4. 实现前端情报流、知识库、搜索和来源管理，并扩展现有模板管理能力。
5. 扩充并评估第三方 X RSS，完善 Email，接入 Langfuse Prompt 管理和评测。

Langfuse 已支持远程 Chat Prompt：筛选 Prompt 名称默认为 `ai-intelligence-filter`，去重 Prompt 名称默认为 `ai-intelligence-dedup`，两者的 User 消息都使用 `{{content_json}}` 接收程序序列化的数据，并发布 `production` label。去重 Prompt 的本地 fallback 位于 `config/prompts/intelligence_dedup.md` 和 `config/prompts/intelligence_dedup_user.md`。将 `.env` 中 `LANGFUSE_ENABLED=true`、公钥和密钥配置好，Worker 会按 `LANGFUSE_CACHE_SECONDS` 刷新，网络失败自动回退到本地 Prompt。`python -m app.worker --prompt-status` 会同时显示筛选、日报/周报和去重 Prompt 的版本及远程状态。不要把 Langfuse 密钥提交到仓库。

Email 和 X 适配器已经加入。Email 使用 IMAP 只读模式，需要设置 `AI_EMAIL_USERNAME`、`AI_EMAIL_PASSWORD`；每个 Newsletter 还应配置 `from_address`，共用发件地址时再配置 `from_name`，避免采集同一邮箱内的无关邮件。TLDR AI 已按这套规则启用。官方 X API v2 Recent Search 仍默认关闭；当前 X 账号通过 `xgo.ing` 提供的第三方 RSS 接入，并在来源配置中标记 `provider: xgo.ing`、`origin: third_party`。该服务可能存在延迟、漏消息或中断，不能视为官方 API。

第一阶段完成后，服务器必须能够在无人操作的情况下持续运行。每个来源按照自己的轮询间隔执行，新消息经过 AI 筛选后自动推送到 Telegram；网络、RSS、LLM 或 Telegram 的短暂失败不能导致 Worker 永久停止。

## 相关文档

- [系统架构](ARCHITECTURE.md)
- [AI 信息源清单](AI%20信息源清单.md)
- [Telegram 链路验证](Telegram%20链路验证.md)
- [Agent 开发约束](AGENTS.md)
- [技术栈](TECH_STACK.md)
- [服务器部署](deploy/README.md)

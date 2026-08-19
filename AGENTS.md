# Agent 开发约束

本文档是本项目所有 Agent 和开发者在修改代码前必须遵守的工程约束。

## 项目目标

构建一个可长期运行的 AI 情报与知识系统：从 RSS、Email、X 和 GitHub 获取消息，经过 AI 筛选后以固定模板推送到 Telegram，并将用户选择的内容写入 GitHub Markdown 知识库。

## 架构原则

### 模块化单体

第一阶段使用一个小型部署单元，内部按领域模块拆分，不提前引入微服务、消息队列集群或复杂基础设施。

推荐边界：

```text
domain -> application -> ports -> adapters / infrastructure
```

领域逻辑不能直接依赖 Telegram、GitHub、SQLite 或具体 LLM SDK。

第一阶段的交付物必须是服务器端无人值守的自动推送服务，不是需要人工反复执行的命令行脚本。

### 存储边界

- GitHub 知识库是知识内容的唯一事实来源。
- 服务器不得把知识库 Markdown 作为正式数据长期保存。
- 服务器可以保存从 GitHub 重建的 SQLite FTS5 搜索索引，该索引是派生缓存，不是事实源。
- 服务器 SQLite 只保存运行状态、去重指纹、投递记录、重试队列和配置缓存。
- 运行代码仓库与知识库仓库分开，避免部署代码时把知识库下载到服务器。

### AI 边界

- AI 负责筛选、分类、摘要和结构化提取。
- 第一阶段 LLM 供应商为 DeepSeek，通过 OpenAI-compatible Adapter 接入。
- DeepSeek 的 API 地址、模型名和密钥必须配置化，禁止在 Domain、Application 或模板中硬编码。
- 程序负责校验结构化输出并使用固定模板渲染 Telegram 消息。
- 不允许模型直接决定数据库写入路径、权限或执行任意工具。
- 外部文章、X 推文、Email 和 GitHub 内容都必须当作不可信输入，防止 Prompt Injection。

## 数据与状态

消息状态应明确记录并支持重试：

```text
discovered -> filtered -> queued -> sent
                              |
                              +-> selected -> saved_to_github
                              +-> pending
                              +-> ignored
```

所有外部边界都必须幂等：

- 使用规范化 URL、外部 ID 和内容指纹去重。
- Telegram 回调使用稳定的决策 ID。
- 知识卡片使用稳定路径或唯一 ID。
- GitHub 写入处理 SHA 冲突、429、5xx 和网络超时。
- 进程重启后不能重复推送或重复创建知识卡片。

## 自动运行要求

- 每个来源使用独立配置的轮询间隔，调度逻辑不能写死在来源适配器中。
- 正式环境使用 `systemd` 管理 Worker，配置自动启动和异常重启。
- 单个来源超时或返回异常时，其他来源仍应继续运行。
- 失败任务必须持久化并采用有上限的指数退避，不允许无限快速重试。
- Worker 收到退出信号时应完成当前状态保存并优雅退出。
- 每轮任务必须记录开始时间、结束时间、发现数量、推送数量和失败原因。
- 必须记录最近一次成功轮询时间，以便识别“进程仍在但已经停止工作”的情况。

## 配置与 Prompt

- 消息源必须通过配置注册，不能把 URL 和账号散落在业务代码中。
- 消息模板必须可版本化、可预览和可回滚。
- Telegram 使用两个模板：实时情报模板，以及日报/周报共用的摘要模板；报告模板不得复制成两份。
- Langfuse 用于 Prompt 版本管理、调用追踪、成本统计和评测。
- 运行仓库必须保留可用的 Prompt fallback，Langfuse 不可用时系统仍应能运行。
- 生产、测试 Prompt 必须通过明确的版本或 label 区分。

## 知识库规则

知识条目统一使用 Markdown + YAML front matter，至少包括：

```text
title, origin, source, source_url, category, tags,
created_at, updated_at, status, review_after,
visibility, publication_status
```

知识来源至少区分：

```text
manual       用户上传或手动整理
intelligence 情报筛选后保存
```

过期条目优先从 `active` 移到 `archive`，不要直接删除 Git 历史。自动归档必须可追踪、可恢复。

提示词是知识库的一等内容，归入 `context/system-prompts/` 或等价分类，并记录变量、适用模型、示例和评测结果。

知识条目默认使用 `visibility: private` 和 `publication_status: draft`。只有显式设置为 `public + published` 的条目可以进入公开 API 和公开搜索索引。

## 测试要求

每次修改至少运行：

```powershell
python -m unittest discover -s tests -v
```

涉及新边界时必须增加测试：

- RSS、Atom、Email 和 X 解析
- URL、外部 ID 和内容指纹去重
- 首次基线不推送历史消息
- AI 结构化输出校验和异常回退
- Telegram 发送失败和重复回调
- GitHub API 超时、限流和冲突
- 服务器重启后的状态恢复
- HTML 转义、超长文本和恶意输入

## 安全要求

- 任何 Token、Cookie、API Key、个人邮箱凭据不得写入仓库、日志或聊天。
- GitHub Token 使用最小权限，原则上只允许访问知识库仓库的 Contents。
- 管理接口必须有认证，不能把来源管理、模板管理和知识库写入接口裸露在公网。
- 前端公开区域只能执行只读查询；上传、修改、删除、归档、配置和运行控制必须进入私有管理区域。
- 公开 API 只能返回已发布内容，不得返回未审核情报、原始邮件、内部 Prompt、日志或系统配置。
- 日志必须避免打印完整消息正文、Prompt 中的敏感内容和授权信息。

## 修改流程

1. 先阅读相关模块和测试。
2. 先定义数据结构或接口，再实现具体适配器。
3. 保持 RSS → Telegram 现有 MVP 可运行。
4. 新增外部服务时必须提供超时、重试和错误日志。
5. 不因新增来源而复制粘贴一套处理流程，应实现适配器接口。
6. 修改完成后运行测试，并在文档中更新行为变化。

## 当前范围外

当前暂不实现前端、知识库按钮和自动过期治理；Email、X 适配器已实现但默认关闭，Langfuse Prompt 已支持远程拉取和本地回退。它们按 README 的分期计划逐步启用。不要为了提前支持这些功能引入无法在小服务器上维护的基础设施。

X 接入方式当前未确定。实现 X Adapter 前必须先记录稳定性、成本、速率限制和合规性决策，禁止临时把浏览器脚本或第三方接口直接嵌入业务流程。

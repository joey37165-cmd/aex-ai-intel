# AI 信息源清单

> 调研日期：2026-08-19  
> 目标：为 X、Telegram、小红书的 AI 内容创作建立高质量输入系统。  
> 当前状态：40 个 RSS/Atom、4 个 Sitemap、3 个 Changelog 和 1 个 Email 来源已启用，共 48 个来源，按来源每 1 至 15 分钟轮询；其中 15 个 RSS 来自 `xgo.ing` 的 X 账号转换服务。VentureBeat AI 因 RSS 停更而关闭，官方 X API 仍默认关闭。

> 程序使用的 RSS 配置文件：[config/sources.json](config/sources.json)。本文件用于记录来源背景、筛选理由和后续观察结论。

## 优先级说明

- **S（核心）**：应进入日常信息流，原创性、速度或实用性突出。
- **A（分类关注）**：在特定主题上有价值，不必每期都读。
- **B（观察）**：可以发现线索，但需要回到原始来源核验。
- **排除**：广告、搬运、灰色内容或低可信内容明显，不进入信息流。

## 第一批：官方公司与官方生态

> 本批次先接入 7 个品牌、9 个官方入口。RSS 入口先进入现有采集器；Sitemap、更新日志和官方 GitHub 入口列入同一批，但要等对应适配器完成后启用。

### 官方公司

| 来源 | 入口 | 接入方式 | 优先级 | 第一批理由 |
|---|---|---|---|---|
| OpenAI | https://openai.com/news/rss.xml | RSS | S | 模型、产品、研究和公司公告最集中 |
| Anthropic | https://www.anthropic.com/sitemap.xml | Sitemap，筛选 `/news/`；已启用 | S | Claude、研究、安全和商业化信息质量高 |
| Anthropic Claude Platform | https://platform.claude.com/docs/en/release-notes/feed.xml | 官方 RSS；已启用 | S | API、SDK、价格、限额和弃用变化最实用 |
| Google DeepMind | https://deepmind.google/blog/rss.xml | RSS | S | Gemini、研究和前沿模型发布 |
| Google AI | https://blog.google/technology/ai/rss/ | RSS + 关键词过滤 | A | Gemini 产品、Google Research 和应用变化 |
| DeepSeek | https://api-docs.deepseek.com/sitemap.xml / https://api-docs.deepseek.com/updates | News Sitemap + Change Log；已启用 | S | API、价格、模型和国内用户实际使用变化 |
| Qwen | https://github.com/QwenLM / https://qwen.ai/blog | 官方 GitHub + 官网 | S | 中文开源模型、Qwen Code 和工具生态 |

### 官方生态与基础设施

| 来源 | 入口 | 接入方式 | 优先级 | 第一批理由 |
|---|---|---|---|---|
| Hugging Face | https://huggingface.co/blog/feed.xml | RSS | S | 开源模型、数据集和工具生态的核心入口 |
| NVIDIA Technical Blog | https://developer.nvidia.com/blog/feed/ | RSS/Atom + AI 主题过滤 | A | GPU、训练、推理和部署基础设施 |

### 第一批暂不接入

以下公司仍然重要，但先放第二批，原因是第一批需要控制数量，且当前没有确认到稳定的官方 RSS 或统一更新入口：

- Meta AI
- xAI
- Microsoft AI

它们不是排除，而是后续通过网页、Email、X 或专用页面适配器接入。

## RSS 接入清单（第一版）

> 这部分是当前可以直接交给采集程序的 RSS/Atom 地址。`已核验`表示在 2026-08-19 能返回 XML/Atom 内容，不代表每篇内容都自动通过质量筛选。

### 官方 AI 公司与生态源

| 优先级 | 来源 | RSS/Atom 地址 | 主要价值 | 状态 |
|---|---|---|---|---|
| S | OpenAI News | https://openai.com/news/rss.xml | 模型、产品、研究和公司公告 | 已核验，启用 |
| S | Google DeepMind Blog | https://deepmind.google/blog/rss.xml | DeepMind 研究和模型发布 | 已核验，启用 |
| A | Google AI Blog | https://blog.google/technology/ai/rss/ | Google AI 产品、模型与研究 | 已核验，启用 |
| S | Hugging Face Blog | https://huggingface.co/blog/feed.xml | 开源模型、数据集和工具生态 | 已核验，启用 |
| A | NVIDIA Technical Blog | https://developer.nvidia.com/blog/feed/ | GPU、推理、训练和 AI 基础设施 | 已核验，启用 |

### 高质量媒体与专家源

| 优先级 | 来源 | RSS/Atom 地址 | 主要价值 | 状态 |
|---|---|---|---|---|
| A | TechCrunch AI | https://techcrunch.com/category/artificial-intelligence/feed/ | AI 产品、公司、融资和行业动态 | 已核验，已启用 |
| A | The Verge AI | https://www.theverge.com/rss/ai-artificial-intelligence/index.xml | 消费级 AI 产品和行业新闻 | 已核验，已启用 |
| S | MIT Technology Review AI | https://www.technologyreview.com/topic/artificial-intelligence/feed/ | 技术趋势、研究、治理和社会影响 | 已核验，已启用 |
| A | VentureBeat AI | https://venturebeat.com/category/ai/feed/ | 企业 AI、产品、融资和应用落地 | RSS 最新停在 2026-05-19，已关闭 |
| A | Ars Technica AI | https://arstechnica.com/ai/feed/ | 技术实现、产品分析和政策新闻 | 已核验，已启用 |
| S | Simon Willison's Weblog | https://simonwillison.net/atom/everything/ | LLM 工程、Agent、工具实测和开发实践 | 已核验，已启用 |
| S | Interconnects | https://www.interconnects.ai/feed | 模型训练、开源模型和产业判断 | 已核验，已启用 |
| A | Import AI | https://jack-clark.net/feed/ | AI 研究、政策、算力和产业趋势 | 已核验，已启用 |
| S | Ahead of AI | https://magazine.sebastianraschka.com/feed | 模型结构、训练方法和开源实践 | 已核验，已启用 |
| A | One Useful Thing | https://www.oneusefulthing.org/feed | AI 工作方法、教育和组织应用 | 已核验，已启用 |
| A | Ben's Bites | https://www.bensbites.com/feed | AI 工具、Agent 和工作流线索 | 已核验，已启用 |

### 有价值但暂不作为 RSS 接入

以下来源有价值，但目前没有确认到稳定、可直接使用的 RSS 地址，暂时保留在网页或后续适配清单：

- Meta AI Blog
- Microsoft AI Blog
- Mistral News
- xAI News
- Anthropic 已进入第一批，但通过 Sitemap 和 Claude 更新日志接入，不放入 RSS 配置。
- DeepSeek 已通过 Official News Sitemap 和 API Change Log 接入，不放入 RSS 配置；Qwen Blog RSS 因长期未更新而不接入。
- 机器之心、量子位等中文媒体

它们后续可以通过网页更新检测、Newsletter 或专用采集器接入，不与 RSS 配置混在一起。

## 一、官方与一手来源

| 优先级 | 来源 | 链接 | 主要价值 | 核验情况 |
|---|---|---|---|---|
| S | OpenAI News | [RSS](https://openai.com/news/rss.xml) | 模型、产品、研究和公司公告 | RSS，最近更新 2026-08-17 |
| S | Anthropic Newsroom | [官网](https://www.anthropic.com/news) | Claude 模型、研究和重要公告 | 最近更新 2026-08-14 |
| S | Claude Platform Release Notes | [更新日志](https://platform.claude.com/docs/en/release-notes/overview) | Claude API、SDK、Console 和功能细节，比新闻稿更具体 | 最近更新 2026-08-11 |
| S | Google DeepMind | [RSS](https://deepmind.google/blog/rss.xml) | DeepMind 研究和模型发布 | 最近更新 2026-08-13 |
| S | Gemini API Changelog | [更新日志](https://ai.google.dev/gemini-api/docs/changelog) | Gemini 模型、API、弃用和价格相关变化 | 已启用专用 Changelog 适配器，最近更新 2026-08-13 |
| S | Hugging Face | [Blog RSS](https://huggingface.co/blog/feed.xml) / [Trending Models](https://huggingface.co/models?sort=trending) | 开源模型、数据集、工具和生态趋势 | Blog 最近更新 2026-08-17 |
| A | Meta AI Blog | [官网](https://ai.meta.com/blog/) | Meta 的开源模型、研究和应用 | 最近更新 2026-07-27 |
| S | Mistral Blog | [官网](https://mistral.ai/news) / [RSS](https://mistral.ai/news/rss) | Mistral 模型、产品和工程更新 | 官方 RSS 已启用，最近更新 2026-08-11 |
| A | xAI News | [官网](https://x.ai/news) | Grok 模型、工具和产品集成 | 最近更新 2026-08-14 |
| S | DeepSeek | [API Change Log](https://api-docs.deepseek.com/updates) / [GitHub](https://github.com/deepseek-ai) | 模型、API、Harness 和开源项目；GitHub 通常最快 | GitHub 持续更新，2026-08-18 已核验 |
| S | Qwen | [GitHub](https://github.com/QwenLM) / [官网](https://qwen.ai/blog) | Qwen 模型、Qwen Code、插件和研究 | GitHub 2026-08-18 有更新；优先看 GitHub |

## 二、综合快讯与邮件

| 优先级 | 来源 | 链接 | 主要价值 | 注意事项 |
|---|---|---|---|---|
| A | TLDR AI | [官网](https://tldr.tech/ai) | 每日总览；经常直链官方博客、论文、GitHub 和技术作者 | 已通过 Gmail IMAP 接入，按发件地址和 `TLDR AI` 显示名称过滤，5 分钟轮询。有赞助区，应作为线索索引而非最终信源 |
| A | The Rundown AI | [官网](https://www.therundown.ai/) / [Feed](https://www.therundown.ai/feed) | 快讯加实用工作流，适合早晨扫读 | 官方 RSS 已启用；与其他 AI 日报存在重复，5 分钟轮询 |
| A | The Batch | [官网](https://www.deeplearning.ai/the-batch/) | Andrew Ng 团队的趋势解释与行业判断 | 官网 Sitemap 期号页已启用；周刊，15 分钟轮询 |
| A | The Neuron | [官网](https://www.theneuron.ai/) / [Feed](https://www.theneuron.ai/feed/) | 每日新闻、工具比较和可复制的 AI 技能 | 官方 Atom 已启用；活跃但重复较多，5 分钟轮询 |
| A | Superhuman AI | [官网](https://www.superhuman.ai/) | 每日 AI 新闻、工具和短教程 | 官网 Sitemap 文章页已启用；内容偏大众化，5 分钟轮询 |
| A | Product Hunt AI Products | [Atom Feed](https://www.producthunt.com/feed) | 新产品、AI 工具、产品趋势和商业机会 | 已启用关键词过滤，10 分钟轮询；官方总 Feed 会混入非 AI 产品 |
| B | Last Week in AI | [官网](https://lastweekin.ai/) | 一周新闻汇总 | 最近核验更新 2026-08-03，适合周度补漏 |

Product Hunt 当前没有稳定的 AI 专题 Feed，已改用官方总 Feed `https://www.producthunt.com/feed`，采集层只保留标题或摘要命中 AI、Agent、LLM、模型、MCP 等关键词的条目。它用于发现产品和变现线索，不把 Product Hunt 的产品描述当作事实结论。

## 三、深度分析、方法与工作流

| 优先级 | 来源 | 链接 | 主要价值 | 核验情况 |
|---|---|---|---|---|
| S | Simon Willison | [Blog/Atom](https://simonwillison.net/atom/everything/) | 新模型实测、开发工具、Agent 与 LLM 工程；常被日报引用 | 最近更新 2026-08-17 |
| S | Interconnects | [官网](https://www.interconnects.ai/) | 模型训练、开源模型、中美实验室竞争和产业判断 | 最近更新 2026-08-17 |
| S | Latent Space | [官网](https://www.latent.space/) | AI 工程、Agent、开发者生态、播客和行业人物 | 最近更新 2026-08-17 |
| S | Ahead of AI | [官网](https://magazine.sebastianraschka.com/) | 模型结构、开源模型、本地 Agent 和技术教育 | 最近更新 2026-08-15 |
| A | Import AI | [官网](https://jack-clark.net/) | 前沿研究、算力、政策和产业趋势 | 周刊，最近更新 2026-08-17 |
| A | AI Snake Oil | [官网](https://www.aisnakeoil.com/) | 反炒作、局限性和批判性分析 | 最近更新 2026-08-05 |
| A | One Useful Thing | [官网](https://www.oneusefulthing.org/) | AI 如何改变工作、教育和组织方法 | 更新频率较低，最近核验 2026-07-23 |
| A | Ben's Bites | [官网](https://www.bensbites.com/) | Agent 实际使用、工具推荐和个人工作流 | 最近更新 2026-08-14 |
| A | Lenny's Newsletter | [官网](https://www.lennysnewsletter.com/) | 产品、增长、创业和 AI 创业者案例 | 最近更新 2026-08-17 |

## 四、X 账号

### 已接入的 X RSS（第三方转换）

以下账号通过 `xgo.ing` 转换为 RSS，复用现有 RSS 采集器；它们不是 X 官方 API，可能存在延迟、漏消息或服务中断。首次接入只建立历史基线，不推送历史推文。

| 账号 | RSS 地址 | 状态 |
|---|---|---|
| [OpenAI @OpenAI](https://x.com/OpenAI) | `https://api.xgo.ing/rss/user/0c0856a69f9f49cf961018c32a0b0049` | 已启用 |
| [Anthropic @AnthropicAI](https://x.com/AnthropicAI) | `https://api.xgo.ing/rss/user/fc28a211471b496682feff329ec616e5` | 已启用 |
| [Google AI @GoogleAI](https://x.com/GoogleAI) | `https://api.xgo.ing/rss/user/4de0bd2d5cef4333a0260dc8157054a7` | 已启用 |
| [Google DeepMind @GoogleDeepMind](https://x.com/GoogleDeepMind) | `https://api.xgo.ing/rss/user/a99538443a484fcc846bdcc8f50745ec` | 已启用 |
| [DeepSeek @deepseek_ai](https://x.com/deepseek_ai) | `https://api.xgo.ing/rss/user/68b610deb24b47ae9a236811563cda86` | 已启用 |
| [Qwen @Alibaba_Qwen](https://x.com/Alibaba_Qwen) | `https://api.xgo.ing/rss/user/80032d016d654eb4afe741ff34b7643d` | 已启用 |
| [Hugging Face @huggingface](https://x.com/huggingface) | `https://api.xgo.ing/rss/user/fc16750ce50741f1b1f05ea1fb29436f` | 已启用 |
| [Andrej Karpathy @karpathy](https://x.com/karpathy) | `https://api.xgo.ing/rss/user/edf707b5c0b248579085f66d7a3c5524` | 已启用 |
| [Andrew Ng @AndrewYNg](https://x.com/AndrewYNg) | `https://api.xgo.ing/rss/user/08b5488b20bc437c8bfc317a52e5c26d` | 已启用 |
| [Rowan Cheung @rowancheung](https://x.com/rowancheung) | `https://api.xgo.ing/rss/user/a636de3cbda0495daabd15b9fd298614` | 已启用 |
| [宝玉 @dotey](https://x.com/dotey) | `https://api.xgo.ing/rss/user/97f1484ae48c430fbbf3438099743674` | 已启用 |
| [OpenAI Developers @OpenAIDevs](https://x.com/OpenAIDevs) | `https://api.xgo.ing/rss/user/971dc1fc90da449bac23e5fad8a33d55` | 已启用 |
| [Sam Altman @sama](https://x.com/sama) | `https://api.xgo.ing/rss/user/e30d4cd223f44bed9d404807105c8927` | 已启用 |
| [Aravind Srinivas @AravSrinivas](https://x.com/AravSrinivas) | `https://api.xgo.ing/rss/user/59e6b63ae9684d11be0ae13d9e7420f2` | 已启用 |
| [歸藏 @op7418](https://x.com/op7418) | `https://api.xgo.ing/rss/user/831fac36aa0a49a9af79f35dc1c9b5d9` | 已启用 |

### 拟建立的私人列表

#### AI-前沿快讯

| 优先级 | 账号 | 价值 |
|---|---|---|
| S | [Ethan Mollick @emollick](https://x.com/emollick) | AI 工作方法、论文和真实实验；会链接 GitHub、OpenAI 研究和外部数据 |
| S | [Sebastian Raschka @rasbt](https://x.com/rasbt) | 模型技术分析、本地 Agent、Meta/Hugging Face 一手链接 |
| S | [swyx @swyx](https://x.com/swyx) | AI 工程、Agent 生态、论文、会议和产品发布 |
| A | [Andrej Karpathy @karpathy](https://x.com/karpathy) | 前沿观点、教育和个人实验；影响力大但更新不固定 |
| A | [Andrew Ng @AndrewYNg](https://x.com/AndrewYNg) | AI 工程教育、行业方法论和课程体系 |
| A | [Aravind Srinivas @AravSrinivas](https://x.com/AravSrinivas) | AI 搜索、Agent、安全研究和 Perplexity 产品动态 |
| B | [Bindu Reddy @bindureddy](https://x.com/bindureddy) | 开源模型、评测和产品观点；需注意自家产品立场 |
| B | [Rowan Cheung @rowancheung](https://x.com/rowancheung) | 高频 AI 快讯和访谈入口；适合发现线索，需回到原始来源 |

#### AI-实战与变现

| 优先级 | 账号 | 价值 |
|---|---|---|
| S | [宝玉 @dotey](https://x.com/dotey) | 中文高质量翻译和分析，经常追到官方博客、论文和 GitHub |
| A | [歸藏 @op7418](https://x.com/op7418) | AI 产品、内容创作、工作流和工具教程，适合寻找中文选题 |
| A | [Greg Isenberg @gregisenberg](https://x.com/gregisenberg) | AI 创业点子、获客、Agent 产品和变现案例；商业导向强 |
| A | [Pieter Levels @levelsio](https://x.com/levelsio) | 独立开发、AI 产品和公开构建经验；非 AI 内容较多，适合列表而非主页 |

### X 反查方法

对可信账号使用以下搜索方式，专门寻找其引用的上游来源：

```text
from:账号 filter:links since:YYYY-MM-DD
```

已验证的典型链路：

- Ethan Mollick -> GitHub 项目、OpenAI 研究报告、Pangram 数据分析。
- Raschka -> Meta Research、Hugging Face 模型卡、个人开源仓库。
- swyx -> 论文、AI Engineer 演讲、产品发布和工程访谈。
- dotey -> Z.ai 官方博客、ACL 论文、GitHub 项目和 DeepSeek Harness 插件。
- op7418 -> 自建开源工具、产品教程和中文工作流。
- TLDR AI -> Z.ai、Hugging Face、Interconnects、arXiv、Simon Willison、Andrew Ng。

## 五、Telegram

| 优先级 | 频道 | 链接 | 结论 |
|---|---|---|---|
| S | Newlearnerの自留地 | [Telegram](https://t.me/NewlearnerChannel) | 中文公开频道中相对可靠；有早晚报、GitHub 项目、独立开发和科技内容。不是纯 AI 频道，也含少量广告 |
| B | AI资源笔记 | [Telegram](https://t.me/aiziyuanbiji) | 经常整理 GitHub 项目和中文长摘要；影响力较小，所有项目需要独立核验 |

### 已排除的 Telegram 来源

- `@AIGeekAPP`：VPN、破解软件、互推和广告比例过高。
- `@zsliangp`：近期被灰色广告、实名任务和烟草广告占据。
- `@LBDBJ`：有技术片段，但重复 VPN 和博彩式广告过多。
- `@AIAutoFrontline`：发帖频率高但单帖浏览量极低，且有大量频道互推，疑似批量生成或网络化内容。

结论：可信的公开中文 AI Telegram 频道数量不足。后续更合理的做法是把可信 RSS、GitHub 和官方网页更新汇入自己的私人 Telegram Bot，而不是继续堆叠公开频道。

## 六、GitHub 发现渠道

### 已接入的 GitHub Release 来源

| 优先级 | 项目 | Release Feed | 主要价值 | 状态 |
|---|---|---|---|---|
| S | Hugging Face Transformers | https://github.com/huggingface/transformers/releases.atom | 模型架构、推理能力和生态兼容更新 | 已启用，5 分钟轮询 |
| A | vLLM | https://github.com/vllm-project/vllm/releases.atom | 模型推理服务、性能和部署更新 | 已启用，5 分钟轮询 |
| A | Browser Use | https://github.com/browser-use/browser-use/releases.atom | 浏览器 Agent 和自动化工作流 | 已启用，5 分钟轮询 |
| A | Langfuse | https://github.com/langfuse/langfuse/releases.atom | LLM 可观测性、Prompt 和评测平台 | 已启用，5 分钟轮询 |
| A | LangChain | https://github.com/langchain-ai/langchain/releases.atom | Agent、工具调用和工作流框架 | 已启用，5 分钟轮询 |

以下 Release 源已核验但暂不启用：AutoGen（长期无近期 Release）、DeepSeek V3、Qwen3（无近期 Release），以及 OpenAI/Anthropic Cookbook（暂无有效 Release 更新）。

### 滚动搜索

[GitHub AI Agents 搜索](https://github.com/search?q=topic%3Aai-agents+stars%3A%3E100&type=repositories&s=updated&o=desc)

建议使用动态条件，而不是只看总星标：

```text
topic:ai-agents created:>最近30天 stars:>100
```

筛选时检查：

1. 创建时间和星标增长速度。
2. 最近提交时间和提交频率。
3. 贡献者数量及是否只有单人一次性提交。
4. 是否有 Release、文档、演示和真实使用案例。
5. 项目是否解决明确问题，而不是只有漂亮 README。

### 最近发现、值得继续观察的项目

| 项目 | 价值 |
|---|---|
| [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) | 官方 Agent Harness，插件化架构 |
| [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 面向 Claude Code/Codex 的产品视频制作 Skill，与内容创作直接相关 |
| [microsoft/skill-recorder](https://github.com/microsoft/skill-recorder) | 把屏幕工作过程重建为可复用 Skill 或自动化 |
| [petergyang/human-review](https://github.com/petergyang/human-review) | 给 AI 生成的 HTML/Markdown 做可视化人工审阅 |
| [mikehasa/agentacct](https://github.com/mikehasa/agentacct) | 跟踪 Agent 做了什么、使用了多少 Token 和成本 |
| [perplexityai/numbat](https://github.com/perplexityai/numbat) | Agent 活动监控、安全检测和审计 |
| [Kritt-ai/open-kritt](https://github.com/Kritt-ai/open-kritt) | 开源 AI 代码安全研究工具 |
| [yanhua1010/self-media-content-workflow](https://github.com/yanhua1010/self-media-content-workflow) | 自媒体内容生产与经营 Skills，和当前目标相关但需继续观察活跃度 |

注意：星标数和短期增长可以被操纵，只能作为发现线索，不能作为推荐依据。

## 七、需要与不需要的消息

### 需要

- 重要模型发布、评测、定价、上下文和 API 变化。
- 最近出现且持续增长的高质量 GitHub AI 项目。
- 有代码、演示、数据或真实结果的 AI 工作流。
- AI 内容生产、图片、视频和自动化工具。
- 有具体产品、客户、定价或收入数据的变现案例。
- 能改变工作方法的实测、教程和研究。
- 同一事件中最接近源头的官方资料。

### 不需要

- 同一新闻的重复转载。
- 没有原始出处的爆料、跑分截图和夸张结论。
- 泛泛而谈的“十大 AI 工具”和“万能提示词”。
- 纯广告、返佣、课程推广和软文。
- 只有星标、没有活跃提交和实际用途的 GitHub 项目。
- 与 AI 内容创作、工作方法和商业机会无关的泛科技内容。
- 把几个月前的内容重新包装成新闻。

## 八、未来推送设想（尚未实施）

- **P0 即时提醒**：重要模型发布、价格/API 重大变化、异常增长的 GitHub 项目、重大产品和商业机会。
- **早间摘要**：昨晚至今晨的重要信息。
- **晚间摘要**：当天信息、值得研究的项目、内容选题和变现信号。
- **每周复盘**：趋势变化、最值得保留的来源、可持续追踪的产品机会。
- 推送目标优先考虑私人 Telegram Bot；飞书可以作为后续知识沉淀渠道。

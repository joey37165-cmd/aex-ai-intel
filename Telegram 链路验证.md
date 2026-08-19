# Telegram 链路验证

这一步只验证以下链路：

```text
OpenAI / Google DeepMind / Google AI / Hugging Face / NVIDIA RSS
                    -> 拉取并解析
                    -> 去重
                    -> Telegram Bot
```

当前不包含 AI 总结、知识库、X、网页或服务器定时任务。

## 1. 本地预览消息

不需要 Telegram 配置：

```powershell
python telegram_poc.py preview
```

只预览一条：

```powershell
python telegram_poc.py --limit 1 preview
```

## 2. 创建 Telegram Bot 并接入频道

1. 在 Telegram 中打开 `@BotFather`。
2. 发送 `/newbot` 并按提示创建机器人。
3. 保存 BotFather 返回的 Token，不要把 Token 发到公开频道或提交到 Git。
4. 打开新机器人，发送 `/start`。
5. 创建一个 Telegram 频道，或打开你已有的频道。
6. 在频道的“管理频道 → 管理员”中添加该 Bot，并授予“发布消息”权限。
7. 在频道里发送一条测试消息，让 Bot API 能发现这个频道。

## 3. 配置 Token 并发现频道 chat_id

复制配置模板：

```powershell
Copy-Item .env.example .env
```

把 Bot Token 填入 `.env` 的 `TELEGRAM_BOT_TOKEN`，暂时不填 `TELEGRAM_CHAT_ID`，然后运行：

```powershell
python telegram_poc.py discover-chat
```

找到 `type` 为 `channel` 的记录，把其中的 `chat_id` 填回 `.env`。

如果频道是公开频道，也可以直接把 `TELEGRAM_CHAT_ID` 设置为 `@频道用户名`。

## 4. 发送固定测试消息到频道

```powershell
python telegram_poc.py send-test
```

频道收到“AI 情报链路测试成功”，说明 Bot 权限和频道配置正确。

## 5. 发送一条真实情报

```powershell
python telegram_poc.py --limit 1 send-latest
```

程序会从第一批五个消息源中选择最新一条，格式化后发送到 Telegram，并将消息 ID 写入：

```text
data/telegram_poc_state.json
```

## 6. 验证正常增量模式

第一次运行会建立基线，不发送历史消息：

```powershell
python telegram_poc.py run
```

之后再次运行时，只会发送没有发送过的新消息：

```powershell
python telegram_poc.py run
```

也可以手动建立基线：

```powershell
python telegram_poc.py bootstrap
```

## Linux 服务器命令

代码放到服务器后，在项目目录创建 `.env`：

```bash
cp .env.example .env
chmod 600 .env
python3 telegram_poc.py preview
python3 telegram_poc.py send-test
python3 telegram_poc.py --limit 1 send-latest
```

完成这三个验证后，再添加 `systemd` 定时运行、AI 筛选和知识库。

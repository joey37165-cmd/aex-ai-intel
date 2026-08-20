# 服务器部署

本项目的生产进程是 `systemd` 管理的 `ai-intel-worker`。服务器只保存运行代码、`.env` 和 SQLite 运行状态，不保存知识库 Markdown。

## 1. 服务器准备

以下命令适用于 Ubuntu/Debian 小服务器：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
sudo mkdir -p /opt/aex-ai-intel
sudo chown "$USER":"$USER" /opt/aex-ai-intel
```

## 2. 拉取私有 GitHub 仓库

推荐使用 GitHub Deploy Key，不要把 Personal Access Token 写入 clone URL。

```bash
ssh-keygen -t ed25519 -f ~/.ssh/aex_ai_intel_deploy -C "aex-ai-intel-server"
cat ~/.ssh/aex_ai_intel_deploy.pub
```

将公钥添加到 GitHub 仓库 `Settings -> Deploy keys`，勾选只读权限，然后：

```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
GIT_SSH_COMMAND="ssh -i ~/.ssh/aex_ai_intel_deploy -o IdentitiesOnly=yes" \
  git clone git@github.com:joey37165-cmd/aex-ai-intel.git /opt/aex-ai-intel
```

## 3. 创建 Python 环境和服务器配置

当前 MVP 只使用 Python 标准库，不需要安装第三方 Python 包：

```bash
cd /opt/aex-ai-intel
python3 -m venv .venv
cp .env.example .env
nano .env
chmod 600 .env
```

至少填写：

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
AI_MODE=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

如果启用 Langfuse 或 TLDR AI Email，再填写对应的 Langfuse/Gmail 配置。密钥只保存在服务器 `/opt/aex-ai-intel/.env`，不要提交到 GitHub。

## 4. 首次建立历史基线

首次部署只记录已有消息，不发送历史内容：

```bash
cd /opt/aex-ai-intel
.venv/bin/python -m app.worker --db data/runtime.db --bootstrap
```

## 5. 安装并启动 systemd 服务

```bash
sudo cp deploy/ai-intel-worker.service /etc/systemd/system/ai-intel-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now ai-intel-worker
sudo systemctl status ai-intel-worker --no-pager
```

查看实时日志：

```bash
sudo journalctl -u ai-intel-worker -f
```

查看采集状态：

```bash
cd /opt/aex-ai-intel
.venv/bin/python -m app.worker --db data/runtime.db --status
```

## 6. 更新代码

```bash
cd /opt/aex-ai-intel
sudo systemctl stop ai-intel-worker
GIT_SSH_COMMAND="ssh -i ~/.ssh/aex_ai_intel_deploy -o IdentitiesOnly=yes" git pull --ff-only origin main
sudo systemctl start ai-intel-worker
sudo journalctl -u ai-intel-worker -n 50 --no-pager
```

更新代码不会覆盖服务器 `.env` 和 `data/runtime.db`。

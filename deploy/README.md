# 服务器部署

本项目的生产进程是 `systemd` 管理的 `ai-intel-worker`。服务器只保存运行代码、`.env` 和 SQLite 运行状态，不保存知识库 Markdown。

## 1. 服务器准备

以下命令适用于 Ubuntu/Debian 小服务器：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
sudo useradd --system --create-home --home-dir /home/aex-ai --shell /usr/sbin/nologin aex-ai
sudo mkdir -p /opt/aex-ai-intel
sudo chown -R aex-ai:aex-ai /opt/aex-ai-intel
```

## 2. 拉取私有 GitHub 仓库

推荐使用 GitHub Deploy Key，不要把 Personal Access Token 写入 clone URL。

以 `aex-ai` 用户生成 Deploy Key：

```bash
sudo -u aex-ai mkdir -p /home/aex-ai/.ssh
sudo -u aex-ai chmod 700 /home/aex-ai/.ssh
sudo -u aex-ai ssh-keygen -t ed25519 -f /home/aex-ai/.ssh/github_deploy -C "aex-ai-intel-server"
sudo cat /home/aex-ai/.ssh/github_deploy.pub
```

将公钥添加到 GitHub 仓库 `Settings -> Deploy keys`，勾选只读权限，然后：

```bash
sudo -u aex-ai sh -c 'ssh-keyscan github.com >> /home/aex-ai/.ssh/known_hosts'
sudo -u aex-ai env GIT_SSH_COMMAND="ssh -i /home/aex-ai/.ssh/github_deploy -o IdentitiesOnly=yes -o UserKnownHostsFile=/home/aex-ai/.ssh/known_hosts" \
  git clone git@github.com:joey37165-cmd/aex-ai-intel.git /opt/aex-ai-intel
```

如果服务器上已经存在 `aex-ai` 用户或代码目录，跳过对应的创建/clone 命令。

## 3. 创建 Python 环境和服务器配置

当前 MVP 只使用 Python 标准库，不需要安装第三方 Python 包：

```bash
cd /opt/aex-ai-intel
sudo -u aex-ai python3 -m venv .venv
sudo -u aex-ai cp .env.example .env
sudoedit /opt/aex-ai-intel/.env
sudo chmod 600 /opt/aex-ai-intel/.env
sudo chown aex-ai:aex-ai /opt/aex-ai-intel/.env
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
sudo -u aex-ai .venv/bin/python -m app.worker --db data/runtime.db --bootstrap
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
sudo -u aex-ai .venv/bin/python -m app.worker --db data/runtime.db --status
```

## 6. 更新代码

```bash
cd /opt/aex-ai-intel
sudo systemctl stop ai-intel-worker
sudo -u aex-ai env GIT_SSH_COMMAND="ssh -i /home/aex-ai/.ssh/github_deploy -o IdentitiesOnly=yes -o UserKnownHostsFile=/home/aex-ai/.ssh/known_hosts" git -C /opt/aex-ai-intel pull --ff-only origin main
sudo systemctl start ai-intel-worker
sudo journalctl -u ai-intel-worker -n 50 --no-pager
```

更新代码不会覆盖服务器 `.env` 和 `data/runtime.db`。

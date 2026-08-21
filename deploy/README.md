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

## 2. 拉取公开 GitHub 仓库

仓库目前是公开的，不需要 GitHub Token 或 Deploy Key：

```bash
sudo -u aex-ai git clone \
  https://github.com/joey37165-cmd/aex-ai-intel.git \
  /opt/aex-ai-intel
```

如果服务器上已经存在 `aex-ai` 用户或代码目录，跳过对应的创建/clone 命令。

## 3. 创建 Python 环境和服务器配置

创建虚拟环境并安装 Worker 与管理 API 依赖：

```bash
cd /opt/aex-ai-intel
sudo -u aex-ai python3 -m venv .venv
sudo -u aex-ai .venv/bin/pip install -r requirements.txt
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
ADMIN_API_TOKEN=请填写至少32个字符的随机值
RUNTIME_DB_PATH=data/runtime.db
```

如果启用 Langfuse 或 TLDR AI Email，再填写对应的 Langfuse/Gmail 配置。密钥只保存在服务器 `/opt/aex-ai-intel/.env`，不要提交到 GitHub。

生成管理 Token：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### 构建模板管理前端

服务器需要 Node.js 20.19+。安装 Node.js 后执行：

```bash
cd /opt/aex-ai-intel/web
sudo -u aex-ai npm ci
sudo -u aex-ai npm run build
```

## 4. 首次建立历史基线

首次部署只记录已有消息，不发送历史内容：

```bash
cd /opt/aex-ai-intel
sudo -u aex-ai .venv/bin/python -m app.worker --db data/runtime.db --bootstrap
```

## 5. 安装并启动 systemd 服务

```bash
sudo cp deploy/ai-intel-worker.service /etc/systemd/system/ai-intel-worker.service
sudo cp deploy/ai-intel-api.service /etc/systemd/system/ai-intel-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now ai-intel-worker
sudo systemctl enable --now ai-intel-api
sudo systemctl status ai-intel-worker --no-pager
sudo systemctl status ai-intel-api --no-pager
```

管理 API 只监听服务器 `127.0.0.1:8000`，不要在安全组中开放 8000 端口。在本机 PowerShell 建立 SSH 隧道：

```powershell
ssh -L 8000:127.0.0.1:8000 admin@47.82.154.127
```

保持该 SSH 窗口运行，然后打开 `http://localhost:8000/`，输入服务器 `.env` 中的 `ADMIN_API_TOKEN`。

查看实时日志：

```bash
sudo journalctl -u ai-intel-worker -f
```

查看采集状态：

```bash
cd /opt/aex-ai-intel
sudo -u aex-ai .venv/bin/python -m app.worker --db data/runtime.db --status
```

立即处理当前到期的日报/周报（部署验证使用，常驻服务会自动调度）：

```bash
cd /opt/aex-ai-intel
sudo -u aex-ai .venv/bin/python -m app.worker --db data/runtime.db --reports-once
```

## 6. 更新代码

```bash
cd /opt/aex-ai-intel
sudo systemctl stop ai-intel-worker
sudo systemctl stop ai-intel-api
sudo -u aex-ai git -C /opt/aex-ai-intel pull --ff-only origin main
sudo -u aex-ai /opt/aex-ai-intel/.venv/bin/pip install -r requirements.txt
cd /opt/aex-ai-intel/web
sudo -u aex-ai npm ci
sudo -u aex-ai npm run build
sudo systemctl start ai-intel-worker
sudo systemctl start ai-intel-api
sudo journalctl -u ai-intel-worker -n 50 --no-pager
sudo journalctl -u ai-intel-api -n 50 --no-pager
```

更新代码不会覆盖服务器 `.env` 和 `data/runtime.db`。

# 🍓 小红书采集系统 - Docker 部署指南

## 域名配置: xhs.aitop.ink

---

## 目录

1. [前置要求](#前置要求)
2. [快速部署](#快速部署)
3. [域名配置](#域名配置)
4. [SSL 证书配置](#ssl-证书配置)
5. [环境变量说明](#环境变量说明)
6. [常用命令](#常用命令)
7. [故障排除](#故障排除)

---

## 前置要求

### 服务器要求

- **操作系统**: Linux (推荐 Ubuntu 20.04/22.04 或 CentOS 7/8)
- **内存**: 最低 1GB，推荐 2GB+
- **磁盘**: 最低 10GB
- **端口**: 80, 443 (HTTPS)

### 软件要求

- Docker 20.10+
- Docker Compose 2.0+

### 安装 Docker (Ubuntu)

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 将当前用户加入 docker 组（可选，避免每次使用 sudo）
sudo usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
docker compose version
```

---

## 快速部署

### 步骤 1: 上传代码到服务器

```bash
# 方式一：使用 Git 克隆
git clone <your-repo-url> /opt/xiaohongshu
cd /opt/xiaohongshu

# 方式二：使用 scp 上传
scp -r ./xiaohongshu user@your-server:/opt/
```

### 步骤 2: 配置环境变量

```bash
cd /opt/xiaohongshu

# 复制配置文件
cp env.production.example .env.production

# 生成密钥（需要 Python）
./deploy.sh keys

# 编辑配置文件，填入生成的密钥
nano .env.production
```

### 步骤 3: 部署应用

```bash
# 给部署脚本添加执行权限
chmod +x deploy.sh

# HTTP 部署（无 SSL）
./deploy.sh http

# 或者：HTTPS 部署
./deploy.sh ssl-init  # 首次需要初始化证书
./deploy.sh ssl
```

---

## 域名配置

### DNS 设置

在你的域名服务商处添加以下 DNS 记录：

| 记录类型 | 主机记录 | 记录值 |
|---------|---------|--------|
| A | xhs | 你的服务器 IP |

### 验证 DNS

```bash
# 检查 DNS 解析
nslookup xhs.aitop.ink
# 或
dig xhs.aitop.ink
```

---

## SSL 证书配置

### 自动获取 Let's Encrypt 证书

```bash
# 1. 确保域名已正确解析到服务器
# 2. 确保 80 端口未被占用

# 初始化 SSL 证书
./deploy.sh ssl-init

# 部署 HTTPS 版本
./deploy.sh ssl
```

### 证书自动续期

Docker Compose 配置已包含 Certbot 自动续期，证书将每 12 小时检查一次并在到期前自动续期。

### 手动续期

```bash
docker compose -f docker-compose.ssl.yml exec certbot certbot renew
docker compose -f docker-compose.ssl.yml exec frontend nginx -s reload
```

---

## 环境变量说明

| 变量名 | 说明 | 示例 |
|-------|------|------|
| `SECRET_KEY` | Flask 密钥，用于会话加密 | 64 位随机字符串 |
| `COOKIE_ENCRYPTION_KEY` | Cookie 加密密钥 (Fernet) | Fernet 生成的密钥 |
| `ADMIN_API_KEY` | 管理员 API 密钥 | 32 位随机字符串 |
| `CORS_ORIGINS` | CORS 允许的域名 | `https://xhs.aitop.ink` |
| `LOG_LEVEL` | 日志级别 | `WARNING` |

### 生成密钥

```bash
# SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# COOKIE_ENCRYPTION_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ADMIN_API_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 常用命令

### 服务管理

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f

# 仅查看后端日志
docker compose logs -f backend

# 重启服务
docker compose restart

# 停止服务
docker compose down

# 重新构建并启动
docker compose up -d --build
```

### HTTPS 版本命令

```bash
# 查看状态
docker compose -f docker-compose.ssl.yml ps

# 查看日志
docker compose -f docker-compose.ssl.yml logs -f

# 停止服务
docker compose -f docker-compose.ssl.yml down
```

### 数据备份

```bash
# 备份数据库
docker cp xhs-backend:/app/xhs_data.db ./backup/xhs_data_$(date +%Y%m%d).db

# 备份媒体文件
docker cp xhs-backend:/app/datas/media_datas ./backup/media_datas_$(date +%Y%m%d)
```

### 数据恢复

```bash
# 恢复数据库
docker cp ./backup/xhs_data.db xhs-backend:/app/xhs_data.db
docker compose restart backend
```

---

## 故障排除

### 问题 1: 端口被占用

```bash
# 检查端口占用
sudo lsof -i :80
sudo lsof -i :443

# 停止占用进程
sudo kill <PID>
```

### 问题 2: 容器无法启动

```bash
# 查看详细日志
docker compose logs backend
docker compose logs frontend

# 检查容器状态
docker ps -a
```

### 问题 3: 无法访问网站

1. 检查防火墙设置：
```bash
# Ubuntu UFW
sudo ufw allow 80
sudo ufw allow 443

# CentOS firewalld
sudo firewall-cmd --add-port=80/tcp --permanent
sudo firewall-cmd --add-port=443/tcp --permanent
sudo firewall-cmd --reload
```

2. 检查云服务器安全组是否开放 80/443 端口

### 问题 4: SSL 证书获取失败

```bash
# 确保域名已解析到服务器 IP
ping xhs.aitop.ink

# 确保 80 端口可访问
curl http://xhs.aitop.ink

# 查看 Certbot 日志
docker compose -f docker-compose.ssl.yml logs certbot
```

### 问题 5: API 请求失败

```bash
# 检查后端健康状态
curl http://localhost:8000/api/health

# 进入后端容器调试
docker exec -it xhs-backend /bin/sh
```

---

## 架构说明

```
                    ┌─────────────────────────────────────┐
                    │           Internet                   │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │     xhs.aitop.ink (DNS)             │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Linux Server                                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Docker Network                             │  │
│  │                                                                │  │
│  │  ┌─────────────────┐         ┌─────────────────────────────┐  │  │
│  │  │    Frontend     │         │         Backend             │  │  │
│  │  │    (Nginx)      │  /api   │    (Flask + Gunicorn)       │  │  │
│  │  │                 │ ──────▶ │                             │  │  │
│  │  │  - 静态文件托管   │         │  - RESTful API             │  │  │
│  │  │  - SSL 终端     │         │  - SQLite 数据库            │  │  │
│  │  │  - 反向代理     │         │  - 数据采集逻辑              │  │  │
│  │  │                 │         │                             │  │  │
│  │  │  Port: 80/443   │         │  Port: 8000                 │  │  │
│  │  └─────────────────┘         └─────────────────────────────┘  │  │
│  │                                                                │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Volumes:                                                            │
│  - xhs-data: 数据库文件                                               │
│  - xhs-media: 媒体文件                                                │
│  - xhs-excel: Excel 导出文件                                          │
│  - certbot: SSL 证书（HTTPS 模式）                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 更新部署

```bash
# 拉取最新代码
git pull origin main

# 重新构建并部署
docker compose down
docker compose build --no-cache
docker compose up -d

# 或使用一条命令
docker compose up -d --build
```

---

## 联系支持

如遇到问题，请检查：
1. Docker 和 Docker Compose 版本
2. 服务器防火墙设置
3. DNS 解析是否正确
4. 环境变量配置是否完整


# 🍓 小红书采集系统 - 自动化部署文档

## 目录

1. [快速开始](#快速开始)
2. [部署命令详解](#部署命令详解)
3. [代码修改后自动部署](#代码修改后自动部署)
4. [自动化脚本说明](#自动化脚本说明)
5. [CI/CD 配置](#cicd-配置)
6. [常见问题](#常见问题)

---

## 快速开始

### 一、首次部署

```bash
# 1. 进入项目目录
cd /home/xhs/xiaohongshu

# 2. 给脚本添加执行权限
chmod +x auto-deploy.sh

# 3. 配置环境变量（首次需要）
cp env.production.example .env.production
nano .env.production  # 编辑配置文件

# 4. 执行完整部署
./auto-deploy.sh deploy
```

### 二、日常更新部署

```bash
# 一键更新（停止旧服务 + 拉取代码 + 重新部署）
./auto-deploy.sh update

# 或者手动控制
./auto-deploy.sh stop     # 先停止
./auto-deploy.sh deploy   # 再部署
```

### 三、快速命令参考

| 命令 | 说明 |
|------|------|
| `./auto-deploy.sh deploy` | 完整部署 |
| `./auto-deploy.sh update` | 拉取代码并更新 |
| `./auto-deploy.sh stop` | 停止所有服务 |
| `./auto-deploy.sh restart` | 重启服务 |
| `./auto-deploy.sh status` | 查看状态 |
| `./auto-deploy.sh logs` | 查看日志 |
| `./auto-deploy.sh backup` | 备份数据 |

---

## 部署命令详解

### 1. 完整部署 (`deploy`)

执行完整的部署流程，包括停止旧服务、构建新镜像、启动服务。

```bash
# 标准部署
./auto-deploy.sh deploy

# 无缓存部署（确保使用最新代码）
./auto-deploy.sh deploy --no-cache
```

**执行流程：**
1. ✅ 检查 Docker 环境
2. ✅ 检查环境配置文件
3. ✅ 停止现有服务（HTTP 和 SSL 版本）
4. ✅ 清理残留容器
5. ✅ 构建 Docker 镜像
6. ✅ 启动新服务
7. ✅ 健康检查

### 2. 快速更新 (`update`)

适用于代码修改后的快速部署，自动拉取 Git 代码。

```bash
./auto-deploy.sh update
```

**执行流程：**
1. ✅ 自动备份数据
2. ✅ 拉取最新 Git 代码
3. ✅ 停止现有服务
4. ✅ 重新构建镜像
5. ✅ 启动新服务

### 3. 停止服务 (`stop`)

安全地停止所有相关服务和容器。

```bash
./auto-deploy.sh stop
```

**会停止：**
- HTTP 版本的所有容器
- SSL 版本的所有容器
- 任何名称包含 `xhs-` 的容器

### 4. 重启服务 (`restart`)

不重新构建，直接重启容器。

```bash
./auto-deploy.sh restart
```

### 5. 查看日志 (`logs`)

```bash
# 查看所有服务日志
./auto-deploy.sh logs

# 只看后端日志
./auto-deploy.sh logs backend

# 只看前端日志
./auto-deploy.sh logs frontend
```

### 6. 数据备份 (`backup`)

```bash
# 快速备份（只备份数据库）
./auto-deploy.sh backup

# 完整备份（包含媒体文件）
./auto-deploy.sh backup --full
```

**备份位置：** `./backups/backup_日期_时间/`

### 7. 回滚 (`rollback`)

恢复到上一个备份版本。

```bash
./auto-deploy.sh rollback
```

---

## 代码修改后自动部署

### 方式一：手动触发部署（推荐）

修改代码后，运行以下命令：

```bash
# 进入项目目录
cd /home/xhs/xiaohongshu

# 执行更新部署
./auto-deploy.sh update
```

### 方式二：Git Hook 自动部署

在服务器上配置 Git Hook，每次 `git push` 后自动部署。

**1. 创建 post-receive hook：**

```bash
# 在服务器的 Git 仓库中
cat > /path/to/repo.git/hooks/post-receive << 'EOF'
#!/bin/bash
# Git Post-Receive Hook - 自动部署

TARGET="/home/xhs/xiaohongshu"
GIT_DIR="/path/to/repo.git"
BRANCH="main"

while read oldrev newrev ref
do
    if [ "$ref" = "refs/heads/$BRANCH" ]; then
        echo "=== 检测到 $BRANCH 分支更新，开始自动部署 ==="
        
        # 更新工作目录
        git --work-tree=$TARGET --git-dir=$GIT_DIR checkout -f $BRANCH
        
        # 执行部署
        cd $TARGET
        ./auto-deploy.sh deploy
        
        echo "=== 部署完成 ==="
    fi
done
EOF

chmod +x /path/to/repo.git/hooks/post-receive
```

### 方式三：监控文件变化自动部署

使用 `inotifywait` 监控代码变化（适用于开发环境）：

```bash
# 安装 inotify-tools
sudo apt-get install inotify-tools

# 创建监控脚本
cat > /home/xhs/xiaohongshu/watch-deploy.sh << 'EOF'
#!/bin/bash
# 监控代码变化自动部署

PROJECT_DIR="/home/xhs/xiaohongshu"
WATCH_DIRS="src backend"

cd $PROJECT_DIR

echo "开始监控代码变化..."

inotifywait -m -r -e modify,create,delete $WATCH_DIRS |
while read path action file; do
    echo "检测到变化: $path$file ($action)"
    
    # 防抖：等待 5 秒，避免频繁触发
    sleep 5
    
    # 执行部署
    ./auto-deploy.sh deploy
done
EOF

chmod +x /home/xhs/xiaohongshu/watch-deploy.sh
```

### 方式四：Webhook 自动部署

配置 GitHub/GitLab Webhook，在代码推送时触发部署。

**1. 创建 Webhook 接收脚本：**

```bash
cat > /home/xhs/xiaohongshu/webhook-deploy.py << 'EOF'
#!/usr/bin/env python3
"""
Webhook 自动部署服务
启动: python3 webhook-deploy.py
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import json
import hmac
import hashlib
import os

# 配置
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'your-secret-key')
PROJECT_DIR = '/home/xhs/xiaohongshu'
DEPLOY_BRANCH = 'main'
PORT = 9000

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        # 验证签名（GitHub）
        signature = self.headers.get('X-Hub-Signature-256', '')
        if signature:
            expected = 'sha256=' + hmac.new(
                WEBHOOK_SECRET.encode(),
                post_data,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected):
                self.send_response(403)
                self.end_headers()
                return
        
        # 解析请求
        try:
            payload = json.loads(post_data)
            ref = payload.get('ref', '')
            
            # 检查是否是目标分支
            if ref == f'refs/heads/{DEPLOY_BRANCH}':
                print(f"检测到 {DEPLOY_BRANCH} 分支更新，开始部署...")
                
                # 异步执行部署
                subprocess.Popen(
                    ['./auto-deploy.sh', 'update'],
                    cwd=PROJECT_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Deployment triggered')
                return
                
        except Exception as e:
            print(f"Error: {e}")
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), WebhookHandler)
    print(f'Webhook server running on port {PORT}...')
    server.serve_forever()
EOF
```

**2. 使用 systemd 管理 Webhook 服务：**

```bash
sudo cat > /etc/systemd/system/xhs-webhook.service << 'EOF'
[Unit]
Description=XHS Webhook Deploy Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/xhs/xiaohongshu
Environment=WEBHOOK_SECRET=your-secret-key
ExecStart=/usr/bin/python3 /home/xhs/xiaohongshu/webhook-deploy.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable xhs-webhook
sudo systemctl start xhs-webhook
```

---

## 自动化脚本说明

### 脚本结构

```
auto-deploy.sh
├── 配置变量
│   ├── PROJECT_NAME    # 项目名称
│   ├── PROJECT_DIR     # 项目目录
│   ├── COMPOSE_FILE    # docker-compose 文件
│   └── BACKUP_DIR      # 备份目录
├── 日志函数
│   ├── log_info()      # 信息日志
│   ├── log_warn()      # 警告日志
│   └── log_error()     # 错误日志
├── 核心函数
│   ├── stop_services() # 停止服务
│   ├── build_images()  # 构建镜像
│   ├── start_services()# 启动服务
│   └── check_health()  # 健康检查
└── 命令实现
    ├── cmd_deploy()    # 完整部署
    ├── cmd_update()    # 快速更新
    ├── cmd_stop()      # 停止服务
    └── ...
```

### 日志文件

部署日志保存在：`/home/xhs/xiaohongshu/deploy.log`

```bash
# 查看部署日志
tail -f /home/xhs/xiaohongshu/deploy.log
```

---

## CI/CD 配置

### GitHub Actions 配置

创建 `.github/workflows/deploy.yml`：

```yaml
name: Deploy to Server

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Server
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /home/xhs/xiaohongshu
            git pull origin main
            ./auto-deploy.sh deploy
```

**配置 Secrets：**
- `SERVER_HOST`: 服务器 IP
- `SERVER_USER`: SSH 用户名
- `SERVER_SSH_KEY`: SSH 私钥

### GitLab CI/CD 配置

创建 `.gitlab-ci.yml`：

```yaml
stages:
  - deploy

deploy_production:
  stage: deploy
  only:
    - main
  script:
    - apt-get update && apt-get install -y openssh-client
    - eval $(ssh-agent -s)
    - echo "$SSH_PRIVATE_KEY" | ssh-add -
    - ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_HOST "cd /home/xhs/xiaohongshu && git pull && ./auto-deploy.sh deploy"
  environment:
    name: production
```

---

## 常见问题

### Q1: 部署时 Docker 构建缓存导致代码未更新

```bash
# 使用无缓存构建
./auto-deploy.sh deploy --no-cache
```

### Q2: 停止服务时有容器无法停止

```bash
# 强制停止所有 xhs 相关容器
docker ps -a --filter "name=xhs-" --format "{{.Names}}" | xargs -r docker stop
docker ps -a --filter "name=xhs-" --format "{{.Names}}" | xargs -r docker rm
```

### Q3: 部署后服务无法访问

```bash
# 1. 检查服务状态
./auto-deploy.sh status

# 2. 查看日志
./auto-deploy.sh logs

# 3. 检查端口占用
sudo lsof -i :80
sudo lsof -i :443

# 4. 检查防火墙
sudo ufw status
```

### Q4: 如何回滚到之前的版本

```bash
# 1. 查看可用备份
ls -la ./backups/

# 2. 执行回滚
./auto-deploy.sh rollback
```

### Q5: 磁盘空间不足

```bash
# 清理 Docker 资源
./auto-deploy.sh clean

# 或手动清理
docker system prune -a
```

---

## 部署检查清单

部署前请确认：

- [ ] `.env.production` 文件已正确配置
- [ ] Docker 和 Docker Compose 已安装
- [ ] 端口 80/443 未被占用
- [ ] 防火墙已开放相应端口
- [ ] 域名已正确解析到服务器

部署后请验证：

- [ ] 前端页面可正常访问
- [ ] API 接口响应正常
- [ ] 用户登录功能正常
- [ ] 数据采集功能正常

---

## 联系与支持

如有问题，请检查：
1. 部署日志：`./deploy.log`
2. Docker 日志：`./auto-deploy.sh logs`
3. 系统日志：`journalctl -u docker`


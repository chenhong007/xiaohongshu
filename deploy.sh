#!/bin/bash
# 小红书采集系统 - 部署脚本
# 域名: xhs.aitop.ink
# 
# 使用方法:
#   chmod +x deploy.sh
#   ./deploy.sh [http|ssl|ssl-init]
#
# 参数说明:
#   http     - 部署 HTTP 版本（无 SSL）
#   ssl      - 部署 HTTPS 版本（需要先初始化证书）
#   ssl-init - 初始化 SSL 证书（首次部署 SSL 时使用）

set -e

DOMAIN="xhs.aitop.ink"
EMAIL="admin@aitop.ink"  # 修改为你的邮箱

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose 未安装"
        exit 1
    fi
    
    log_info "Docker 环境检查通过"
}

# 检查环境配置文件
check_env() {
    if [ ! -f ".env.production" ]; then
        log_warn "未找到 .env.production 文件"
        log_info "正在从示例文件创建..."
        cp env.production.example .env.production
        log_warn "请编辑 .env.production 文件，设置安全密钥后重新运行此脚本"
        exit 1
    fi
    
    # 检查是否修改了默认值
    if grep -q "请替换" .env.production; then
        log_error ".env.production 中仍包含默认值，请修改后重试"
        exit 1
    fi
    
    log_info "环境配置检查通过"
}

# 生成密钥
generate_keys() {
    log_info "生成安全密钥..."
    
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    ADMIN_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)
    
    # 尝试生成 Fernet 密钥
    FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "")
    
    echo ""
    echo "=========================================="
    echo "请将以下密钥复制到 .env.production 文件:"
    echo "=========================================="
    echo "SECRET_KEY=${SECRET_KEY}"
    if [ -n "$FERNET_KEY" ]; then
        echo "COOKIE_ENCRYPTION_KEY=${FERNET_KEY}"
    else
        echo "# COOKIE_ENCRYPTION_KEY 需要手动生成（需要 cryptography 库）"
    fi
    echo "ADMIN_API_KEY=${ADMIN_KEY}"
    echo "=========================================="
}

# 部署 HTTP 版本
deploy_http() {
    log_info "开始部署 HTTP 版本..."
    
    check_env
    
    # 加载环境变量
    export $(cat .env.production | grep -v '^#' | xargs)
    
    # 构建并启动
    docker compose down 2>/dev/null || true
    docker compose build
    docker compose up -d
    
    log_info "部署完成！"
    echo ""
    echo "=========================================="
    echo "🍓 小红书采集系统已启动"
    echo "=========================================="
    echo "访问地址: http://${DOMAIN}"
    echo ""
    echo "查看日志: docker compose logs -f"
    echo "停止服务: docker compose down"
    echo "=========================================="
}

# 初始化 SSL 证书
init_ssl() {
    log_info "初始化 SSL 证书..."
    
    # 创建证书目录
    mkdir -p certbot/conf certbot/www
    
    # 启动临时 Nginx 服务（用于证书验证）
    log_info "启动临时 Nginx 服务..."
    
    # 创建临时 Nginx 配置
    mkdir -p nginx-temp
    cat > nginx-temp/default.conf << EOF
server {
    listen 80;
    server_name ${DOMAIN};
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 200 'SSL initialization in progress';
        add_header Content-Type text/plain;
    }
}
EOF

    # 启动临时容器
    docker run -d --name nginx-temp \
        -p 80:80 \
        -v $(pwd)/nginx-temp:/etc/nginx/conf.d \
        -v $(pwd)/certbot/www:/var/www/certbot \
        nginx:alpine
    
    sleep 2
    
    # 获取证书
    log_info "正在获取 Let's Encrypt 证书..."
    docker run --rm \
        -v $(pwd)/certbot/conf:/etc/letsencrypt \
        -v $(pwd)/certbot/www:/var/www/certbot \
        certbot/certbot certonly \
        --webroot -w /var/www/certbot \
        --email ${EMAIL} \
        --agree-tos \
        --no-eff-email \
        -d ${DOMAIN}
    
    # 停止临时容器
    docker stop nginx-temp
    docker rm nginx-temp
    rm -rf nginx-temp
    
    log_info "SSL 证书获取成功！"
    log_info "现在可以运行 './deploy.sh ssl' 部署 HTTPS 版本"
}

# 部署 SSL 版本
deploy_ssl() {
    log_info "开始部署 HTTPS 版本..."
    
    check_env
    
    # 检查证书是否存在
    if [ ! -d "certbot/conf/live/${DOMAIN}" ]; then
        log_error "SSL 证书不存在，请先运行 './deploy.sh ssl-init' 初始化证书"
        exit 1
    fi
    
    # 加载环境变量
    export $(cat .env.production | grep -v '^#' | xargs)
    
    # 构建并启动
    docker compose -f docker-compose.ssl.yml down 2>/dev/null || true
    docker compose -f docker-compose.ssl.yml build
    docker compose -f docker-compose.ssl.yml up -d
    
    log_info "部署完成！"
    echo ""
    echo "=========================================="
    echo "🍓 小红书采集系统已启动 (HTTPS)"
    echo "=========================================="
    echo "访问地址: https://${DOMAIN}"
    echo ""
    echo "查看日志: docker compose -f docker-compose.ssl.yml logs -f"
    echo "停止服务: docker compose -f docker-compose.ssl.yml down"
    echo "=========================================="
}

# 主函数
main() {
    echo ""
    echo "🍓 小红书采集系统 - 部署脚本"
    echo ""
    
    check_docker
    
    case "${1:-http}" in
        http)
            deploy_http
            ;;
        ssl)
            deploy_ssl
            ;;
        ssl-init)
            init_ssl
            ;;
        keys)
            generate_keys
            ;;
        *)
            echo "用法: $0 [http|ssl|ssl-init|keys]"
            echo ""
            echo "命令说明:"
            echo "  http      部署 HTTP 版本（默认）"
            echo "  ssl       部署 HTTPS 版本"
            echo "  ssl-init  初始化 SSL 证书"
            echo "  keys      生成安全密钥"
            exit 1
            ;;
    esac
}

main "$@"


#!/bin/bash
# 小红书采集系统 - 多服务部署脚本
# 适用于服务器上已有其他服务的场景
#
# 使用方法:
#   chmod +x deploy-multi.sh
#   ./deploy-multi.sh [setup|start|stop|logs]

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装"
        exit 1
    fi
}

# 检查 nginx-proxy 网络
check_network() {
    if ! docker network inspect nginx-proxy >/dev/null 2>&1; then
        log_error "nginx-proxy 网络不存在"
        log_info "请先初始化 Nginx 代理: cd nginx-proxy && ./setup.sh"
        exit 1
    fi
}

# 检查环境变量
check_env() {
    if [ ! -f ".env.production" ]; then
        log_warn "未找到 .env.production"
        cp env.production.example .env.production
        log_warn "请编辑 .env.production 后重新运行"
        exit 1
    fi
    
    if grep -q "请替换" .env.production; then
        log_error ".env.production 包含默认值，请修改后重试"
        exit 1
    fi
}

# 初始化设置
setup() {
    log_info "初始化 Nginx 代理..."
    
    cd nginx-proxy
    chmod +x setup.sh
    ./setup.sh
    cd ..
    
    log_info "初始化完成！"
}

# 启动服务
start() {
    log_info "启动小红书采集系统..."
    
    check_network
    check_env
    
    export $(cat .env.production | grep -v '^#' | xargs)
    
    docker compose -f docker-compose.multi.yml down 2>/dev/null || true
    docker compose -f docker-compose.multi.yml build
    docker compose -f docker-compose.multi.yml up -d
    
    # 复制站点配置到 nginx-proxy
    if [ -f "nginx-proxy/conf.d/xhs.aitop.ink.conf" ]; then
        log_info "站点配置已存在"
    fi
    
    # 重载 nginx-proxy 配置
    docker exec nginx-proxy nginx -s reload 2>/dev/null || true
    
    log_info "部署完成！"
    echo ""
    echo "=========================================="
    echo "🍓 小红书采集系统已启动"
    echo "=========================================="
    echo "访问地址: http://xhs.aitop.ink"
    echo ""
    echo "查看日志: ./deploy-multi.sh logs"
    echo "停止服务: ./deploy-multi.sh stop"
    echo "=========================================="
}

# 停止服务
stop() {
    log_info "停止小红书采集系统..."
    docker compose -f docker-compose.multi.yml down
    log_info "服务已停止"
}

# 查看日志
logs() {
    docker compose -f docker-compose.multi.yml logs -f
}

# 主函数
main() {
    check_docker
    
    case "${1:-start}" in
        setup)
            setup
            ;;
        start)
            start
            ;;
        stop)
            stop
            ;;
        logs)
            logs
            ;;
        *)
            echo "用法: $0 [setup|start|stop|logs]"
            echo ""
            echo "命令说明:"
            echo "  setup   首次部署，初始化 Nginx 代理"
            echo "  start   启动服务（默认）"
            echo "  stop    停止服务"
            echo "  logs    查看日志"
            exit 1
            ;;
    esac
}

main "$@"


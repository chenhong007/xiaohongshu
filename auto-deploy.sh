#!/bin/bash
# ============================================================
# 🍓 小红书采集系统 - 自动化部署脚本
# ============================================================
# 
# 使用方法:
#   chmod +x auto-deploy.sh
#   ./auto-deploy.sh [命令]
#
# 可用命令:
#   deploy     - 完整部署（停止旧服务 + 重新构建 + 启动）
#   update     - 快速更新（拉取代码 + 重新部署）
#   restart    - 重启所有服务
#   stop       - 停止所有服务
#   status     - 查看服务状态
#   logs       - 查看实时日志
#   backup     - 备份数据
#   clean      - 清理无用的 Docker 资源
#   rollback   - 回滚到上一个版本
#
# ============================================================

set -e

# 配置变量
PROJECT_NAME="xiaohongshu"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="docker-compose.yml"
SSL_COMPOSE_FILE="docker-compose.ssl.yml"
BACKUP_DIR="${PROJECT_DIR}/backups"
LOG_FILE="${PROJECT_DIR}/deploy.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================
# 日志函数
# ============================================================

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${BLUE}[$timestamp]${NC} $1"
    echo "[$timestamp] $1" >> "$LOG_FILE"
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    log "[INFO] $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    log "[WARN] $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    log "[ERROR] $1"
}

log_step() {
    echo -e "${CYAN}======================================${NC}"
    echo -e "${CYAN}>> $1${NC}"
    echo -e "${CYAN}======================================${NC}"
    log ">> $1"
}

# ============================================================
# 工具函数
# ============================================================

# 检查是否使用 SSL
is_ssl_mode() {
    if [ -f "${PROJECT_DIR}/.ssl_mode" ] || [ -d "${PROJECT_DIR}/certbot/conf/live" ]; then
        return 0
    fi
    return 1
}

# 获取正确的 compose 文件
get_compose_file() {
    if is_ssl_mode; then
        echo "$SSL_COMPOSE_FILE"
    else
        echo "$COMPOSE_FILE"
    fi
}

# 检查 Docker 是否运行
check_docker() {
    if ! docker info &> /dev/null; then
        log_error "Docker 未运行，请先启动 Docker"
        exit 1
    fi
}

# 检查端口是否被占用
check_port_conflict() {
    local port=$1
    local container_name=$2
    
    # 检查是否有其他容器占用该端口
    local blocking_container=$(docker ps --filter "publish=${port}" --format "{{.Names}}" | grep -v "^${container_name}$" | head -1)
    
    if [ -n "$blocking_container" ]; then
        log_warn "⚠️  端口 ${port} 被容器 '${blocking_container}' 占用"
        echo ""
        echo -e "${YELLOW}解决方案:${NC}"
        echo "  1. 停止占用端口的容器: docker stop ${blocking_container} && docker rm ${blocking_container}"
        echo "  2. 或者修改本项目使用的端口"
        echo ""
        read -p "是否自动停止 ${blocking_container} 容器？(y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "停止容器 ${blocking_container}..."
            docker stop "$blocking_container" && docker rm "$blocking_container"
            log_info "✅ 容器已停止"
        else
            log_error "请先手动处理端口冲突，然后重新运行部署"
            exit 1
        fi
    fi
}

# 检查所有需要的端口
check_all_ports() {
    log_info "检查端口占用情况..."
    check_port_conflict 80 "xhs-frontend"
    check_port_conflict 443 "xhs-frontend"
}

# 检查环境配置
check_env() {
    if [ ! -f "${PROJECT_DIR}/.env.production" ]; then
        log_error "未找到 .env.production 文件"
        log_info "请先复制并配置: cp env.production.example .env.production"
        exit 1
    fi
}

# 加载环境变量
load_env() {
    if [ -f "${PROJECT_DIR}/.env.production" ]; then
        export $(cat "${PROJECT_DIR}/.env.production" | grep -v '^#' | xargs)
    fi
}

# ============================================================
# 核心功能函数
# ============================================================

# 停止所有服务
stop_services() {
    log_step "停止现有服务..."
    
    cd "$PROJECT_DIR"
    
    # 停止 HTTP 版本
    if docker compose ps --quiet 2>/dev/null | grep -q .; then
        log_info "停止 HTTP 服务..."
        docker compose down --remove-orphans 2>/dev/null || true
    fi
    
    # 停止 SSL 版本
    if docker compose -f "$SSL_COMPOSE_FILE" ps --quiet 2>/dev/null | grep -q .; then
        log_info "停止 SSL 服务..."
        docker compose -f "$SSL_COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
    fi
    
    # 确保所有相关容器都停止
    local containers=$(docker ps -a --filter "name=xhs-" --format "{{.Names}}" 2>/dev/null)
    if [ -n "$containers" ]; then
        log_info "清理残留容器..."
        echo "$containers" | xargs -r docker stop 2>/dev/null || true
        echo "$containers" | xargs -r docker rm 2>/dev/null || true
    fi
    
    log_info "所有服务已停止"
}

# 构建镜像
build_images() {
    log_step "构建 Docker 镜像..."
    
    cd "$PROJECT_DIR"
    local compose_file=$(get_compose_file)
    
    # 使用 --no-cache 确保获取最新代码
    if [ "$1" == "--no-cache" ]; then
        log_info "无缓存构建..."
        docker compose -f "$compose_file" build --no-cache
    else
        docker compose -f "$compose_file" build
    fi
    
    log_info "镜像构建完成"
}

# 启动服务
start_services() {
    log_step "启动服务..."
    
    cd "$PROJECT_DIR"
    load_env
    
    local compose_file=$(get_compose_file)
    
    docker compose -f "$compose_file" up -d
    
    # 等待服务启动
    log_info "等待服务启动..."
    sleep 5
    
    # 检查服务状态
    check_health
    
    log_info "服务启动完成"
}

# 检查服务健康状态
check_health() {
    log_step "检查服务健康状态..."
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://localhost/api/health &>/dev/null; then
            log_info "✅ 后端服务健康"
            break
        fi
        
        attempt=$((attempt + 1))
        if [ $attempt -eq $max_attempts ]; then
            log_warn "后端服务可能未完全启动，请手动检查"
        fi
        sleep 2
    done
    
    # 显示服务状态
    show_status
}

# 显示服务状态
show_status() {
    log_step "服务状态"
    
    cd "$PROJECT_DIR"
    local compose_file=$(get_compose_file)
    
    docker compose -f "$compose_file" ps
}

# ============================================================
# 命令实现
# ============================================================

# 完整部署
cmd_deploy() {
    local no_cache=""
    if [ "$1" == "--no-cache" ]; then
        no_cache="--no-cache"
    fi
    
    log_step "🚀 开始完整部署"
    
    check_docker
    check_env
    
    stop_services
    check_all_ports
    build_images $no_cache
    start_services
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}🍓 部署完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    
    if is_ssl_mode; then
        echo "访问地址: https://xhs.topai.ink"
    else
        echo "访问地址: http://localhost 或 http://服务器IP"
    fi
    
    echo ""
    echo "常用命令:"
    echo "  ./auto-deploy.sh status  - 查看状态"
    echo "  ./auto-deploy.sh logs    - 查看日志"
    echo "  ./auto-deploy.sh stop    - 停止服务"
}

# 快速更新（拉取代码后重新部署）
cmd_update() {
    log_step "🔄 开始快速更新"
    
    check_docker
    check_env
    
    cd "$PROJECT_DIR"
    
    # 备份数据
    cmd_backup
    
    # 拉取最新代码（如果是 git 仓库）
    if [ -d ".git" ]; then
        log_info "拉取最新代码..."
        git pull origin $(git rev-parse --abbrev-ref HEAD) || {
            log_warn "Git pull 失败，请手动处理冲突"
        }
    fi
    
    # 重新部署
    stop_services
    check_all_ports
    build_images
    start_services
    
    log_info "✅ 更新完成"
}

# 重启服务
cmd_restart() {
    log_step "🔄 重启服务"
    
    cd "$PROJECT_DIR"
    local compose_file=$(get_compose_file)
    
    docker compose -f "$compose_file" restart
    
    sleep 3
    show_status
    
    log_info "重启完成"
}

# 停止服务
cmd_stop() {
    stop_services
    echo ""
    echo -e "${GREEN}所有服务已停止${NC}"
}

# 查看日志
cmd_logs() {
    cd "$PROJECT_DIR"
    local compose_file=$(get_compose_file)
    local service="$1"
    
    if [ -n "$service" ]; then
        docker compose -f "$compose_file" logs -f "$service"
    else
        docker compose -f "$compose_file" logs -f
    fi
}

# 备份数据
cmd_backup() {
    log_step "📦 备份数据"
    
    mkdir -p "$BACKUP_DIR"
    
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_name="backup_${timestamp}"
    local backup_path="${BACKUP_DIR}/${backup_name}"
    
    mkdir -p "$backup_path"
    
    # 备份数据库
    if docker ps --format '{{.Names}}' | grep -q "xhs-backend"; then
        log_info "备份数据库..."
        docker cp xhs-backend:/app/xhs_data.db "${backup_path}/xhs_data.db" 2>/dev/null || {
            log_warn "数据库文件可能不存在"
        }
    fi
    
    # 备份媒体文件（可选）
    if [ "$1" == "--full" ]; then
        log_info "备份媒体文件..."
        docker cp xhs-backend:/app/datas "${backup_path}/datas" 2>/dev/null || true
    fi
    
    # 清理旧备份（保留最近 5 个）
    cd "$BACKUP_DIR"
    ls -t | tail -n +6 | xargs -r rm -rf
    
    log_info "备份完成: ${backup_path}"
}

# 回滚到上一个版本
cmd_rollback() {
    log_step "⏪ 回滚到上一个版本"
    
    if [ ! -d "$BACKUP_DIR" ]; then
        log_error "没有可用的备份"
        exit 1
    fi
    
    # 获取最新的备份
    local latest_backup=$(ls -t "$BACKUP_DIR" | head -1)
    
    if [ -z "$latest_backup" ]; then
        log_error "没有可用的备份"
        exit 1
    fi
    
    local backup_path="${BACKUP_DIR}/${latest_backup}"
    
    log_info "使用备份: ${latest_backup}"
    
    # 恢复数据库
    if [ -f "${backup_path}/xhs_data.db" ]; then
        docker cp "${backup_path}/xhs_data.db" xhs-backend:/app/xhs_data.db
        log_info "数据库已恢复"
    fi
    
    # 重启后端服务
    docker restart xhs-backend
    
    log_info "回滚完成"
}

# 清理 Docker 资源
cmd_clean() {
    log_step "🧹 清理 Docker 资源"
    
    # 清理未使用的镜像
    log_info "清理悬空镜像..."
    docker image prune -f
    
    # 清理未使用的卷（谨慎！）
    read -p "是否清理未使用的 Docker 卷？(y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker volume prune -f
    fi
    
    # 清理构建缓存
    log_info "清理构建缓存..."
    docker builder prune -f
    
    log_info "清理完成"
}

# 进入后端容器
cmd_shell() {
    log_info "进入后端容器..."
    docker exec -it xhs-backend /bin/sh
}

# 显示帮助
show_help() {
    echo ""
    echo -e "${CYAN}🍓 小红书采集系统 - 自动化部署脚本${NC}"
    echo ""
    echo "使用方法: $0 [命令] [选项]"
    echo ""
    echo "可用命令:"
    echo -e "  ${GREEN}deploy${NC}     完整部署（停止旧服务 + 重新构建 + 启动）"
    echo "             选项: --no-cache  无缓存构建"
    echo -e "  ${GREEN}update${NC}     快速更新（拉取代码 + 备份 + 重新部署）"
    echo -e "  ${GREEN}restart${NC}    重启所有服务"
    echo -e "  ${GREEN}stop${NC}       停止所有服务"
    echo -e "  ${GREEN}status${NC}     查看服务状态"
    echo -e "  ${GREEN}logs${NC}       查看实时日志"
    echo "             选项: [服务名]  只看特定服务（backend/frontend）"
    echo -e "  ${GREEN}backup${NC}     备份数据"
    echo "             选项: --full  完整备份（含媒体文件）"
    echo -e "  ${GREEN}rollback${NC}   回滚到上一个版本"
    echo -e "  ${GREEN}clean${NC}      清理无用的 Docker 资源"
    echo -e "  ${GREEN}shell${NC}      进入后端容器"
    echo -e "  ${GREEN}help${NC}       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 deploy              # 完整部署"
    echo "  $0 deploy --no-cache   # 无缓存完整部署"
    echo "  $0 update              # 拉取代码并更新"
    echo "  $0 logs backend        # 查看后端日志"
    echo ""
}

# ============================================================
# 主入口
# ============================================================

main() {
    case "${1:-help}" in
        deploy)
            cmd_deploy "$2"
            ;;
        update)
            cmd_update
            ;;
        restart)
            cmd_restart
            ;;
        stop)
            cmd_stop
            ;;
        status)
            show_status
            ;;
        logs)
            cmd_logs "$2"
            ;;
        backup)
            cmd_backup "$2"
            ;;
        rollback)
            cmd_rollback
            ;;
        clean)
            cmd_clean
            ;;
        shell)
            cmd_shell
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 切换到项目目录
cd "$PROJECT_DIR"

main "$@"


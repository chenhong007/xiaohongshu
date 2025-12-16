#!/bin/bash
# ============================================================
# 🍓 小红书采集系统 - 自动化部署脚本
# ============================================================
# 
# 使用方法:
#   chmod +x auto-deploy.sh
#   ./auto-deploy.sh [命令]
#
# 基础命令:
#   deploy     - 完整部署（停止旧服务 + 重新构建 + 启动）
#   update     - 快速更新（拉取代码 + 重新部署）
#   restart    - 重启所有服务
#   stop       - 停止所有服务
#   status     - 查看服务状态
#   logs       - 查看实时日志
#
# SSL/HTTPS 命令:
#   ssl-init   - 初始化 SSL 证书（首次启用 HTTPS）
#   ssl-enable - 启用 SSL 模式
#   ssl-disable- 禁用 SSL 模式
#   ssl-renew  - 续期 SSL 证书
#   ssl-status - 查看 SSL 状态
#
# 其他命令:
#   backup     - 备份数据
#   verify     - 验证镜像代码版本
#   clean      - 清理无用的 Docker 资源
#   clean-cache- 清理 Python 缓存文件（__pycache__、.pyc 等）
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

# SSL 配置
SSL_DOMAIN="xhs.topai.ink"
SSL_EMAIL="admin@topai.ink"
CERTBOT_DIR="${PROJECT_DIR}/certbot"

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

# 检查并停止系统 Nginx 服务
stop_system_nginx() {
    log_info "检查系统 Nginx 服务..."
    
    # 检查 systemd nginx 服务
    if systemctl is-active --quiet nginx 2>/dev/null; then
        log_warn "发现系统 Nginx 服务正在运行"
        log_info "停止系统 Nginx 服务..."
        sudo systemctl stop nginx 2>/dev/null || true
        sudo systemctl disable nginx 2>/dev/null || true
        log_info "✅ 系统 Nginx 已停止并禁用"
    fi
    
    # 检查是否有独立的 nginx 进程（非 Docker）
    local nginx_pids=$(pgrep -x nginx 2>/dev/null | head -5)
    if [ -n "$nginx_pids" ]; then
        # 检查是否是 Docker 容器内的进程
        for pid in $nginx_pids; do
            local cgroup=$(cat /proc/$pid/cgroup 2>/dev/null | head -1)
            if [[ ! "$cgroup" =~ "docker" ]]; then
                log_warn "发现非 Docker 的 nginx 进程 (PID: $pid)"
                log_info "终止系统 nginx 进程..."
                sudo kill -9 $pid 2>/dev/null || true
            fi
        done
    fi
}

# 检查端口是否被占用（增强版：包括系统进程）
check_port_conflict() {
    local port=$1
    local container_name=$2
    
    # 先检查系统进程占用
    local system_process=$(sudo lsof -i :${port} -t 2>/dev/null | head -1)
    if [ -n "$system_process" ]; then
        local process_name=$(ps -p $system_process -o comm= 2>/dev/null)
        local is_docker_count=$(cat /proc/$system_process/cgroup 2>/dev/null | grep -c "docker" 2>/dev/null || echo "0")
        local is_docker=${is_docker_count:-0}
        
        if [ "$is_docker" = "0" ]; then
            log_warn "⚠️  端口 ${port} 被系统进程 '${process_name}' (PID: ${system_process}) 占用"
            
            if [ "$process_name" == "nginx" ]; then
                log_info "检测到系统 Nginx，尝试停止..."
                stop_system_nginx
                return 0
            fi
            
            echo ""
            echo -e "${YELLOW}解决方案:${NC}"
            echo "  1. 停止占用端口的进程: sudo kill $system_process"
            echo "  2. 或者: sudo systemctl stop ${process_name}"
            echo ""
            read -p "是否自动停止该进程？(y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo kill -9 $system_process 2>/dev/null || true
                sleep 1
                log_info "✅ 进程已停止"
            else
                log_error "请先手动处理端口冲突，然后重新运行部署"
                exit 1
            fi
            return 0
        fi
    fi
    
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
    
    # 先停止系统 Nginx
    stop_system_nginx
    
    # 检查端口冲突
    check_port_conflict 80 "xhs-frontend"
    if is_ssl_mode; then
        check_port_conflict 443 "xhs-frontend"
    fi
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

# 获取当前 Git commit hash
get_git_commit() {
    if [ -d ".git" ]; then
        git rev-parse HEAD 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# 获取当前 Git commit 短 hash
get_git_commit_short() {
    if [ -d ".git" ]; then
        git rev-parse --short HEAD 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# 检查是否有未提交的更改
check_git_clean() {
    if [ -d ".git" ]; then
        if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
            return 1  # 有未提交的更改
        fi
    fi
    return 0  # 干净的工作区
}

# 清理 Python 缓存文件（__pycache__ 和 .pyc）
clean_python_cache() {
    log_info "清理 Python 缓存文件..."
    
    cd "$PROJECT_DIR"
    
    # 删除所有 __pycache__ 目录
    local pycache_count=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)
    if [ "$pycache_count" -gt 0 ]; then
        find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        log_info "  已删除 ${pycache_count} 个 __pycache__ 目录"
    fi
    
    # 删除所有 .pyc 文件
    local pyc_count=$(find . -type f -name "*.pyc" 2>/dev/null | wc -l)
    if [ "$pyc_count" -gt 0 ]; then
        find . -type f -name "*.pyc" -delete 2>/dev/null || true
        log_info "  已删除 ${pyc_count} 个 .pyc 文件"
    fi
    
    # 删除所有 .pyo 文件（Python 优化字节码）
    local pyo_count=$(find . -type f -name "*.pyo" 2>/dev/null | wc -l)
    if [ "$pyo_count" -gt 0 ]; then
        find . -type f -name "*.pyo" -delete 2>/dev/null || true
        log_info "  已删除 ${pyo_count} 个 .pyo 文件"
    fi
    
    if [ "$pycache_count" -eq 0 ] && [ "$pyc_count" -eq 0 ] && [ "$pyo_count" -eq 0 ]; then
        log_info "  无需清理，未发现 Python 缓存文件"
    else
        log_info "✅ Python 缓存清理完成"
    fi
}

# 自动提交并推送本地更改
auto_commit_push() {
    if [ -d ".git" ]; then
        # 提交前先清理 Python 缓存文件，避免同步到远程仓库
        clean_python_cache
        
        if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
            log_warn "检测到未提交的本地更改，正在自动提交..."
            
            git add .
            git commit -m "Auto deploy: save local changes $(date '+%Y-%m-%d %H:%M:%S')"
            
            log_info "正在推送到远程仓库..."
            git push origin $(git rev-parse --abbrev-ref HEAD) || {
                log_warn "Git push 失败，虽然代码已提交到本地仓库，但未能推送到远程。"
                log_warn "请稍后手动检查 git push。"
            }
            
            log_info "✅ 本地更改已提交"
        fi
    fi
}

# 获取已部署的版本信息
get_deployed_version() {
    local version_file="${PROJECT_DIR}/.deploy_version"
    if [ -f "$version_file" ]; then
        source "$version_file"
        echo "$GIT_COMMIT"
    else
        echo ""
    fi
}

# 获取已部署的版本短 hash
get_deployed_version_short() {
    local version_file="${PROJECT_DIR}/.deploy_version"
    if [ -f "$version_file" ]; then
        source "$version_file"
        echo "$GIT_COMMIT_SHORT"
    else
        echo ""
    fi
}

# 获取构建时间
get_deployed_build_time() {
    local version_file="${PROJECT_DIR}/.deploy_version"
    if [ -f "$version_file" ]; then
        source "$version_file"
        echo "$BUILD_TIME"
    else
        echo ""
    fi
}

# 验证镜像代码版本
verify_image_version() {
    log_step "🔍 验证镜像代码版本..."
    
    cd "$PROJECT_DIR"
    local current_commit=$(get_git_commit)
    local current_commit_short=$(get_git_commit_short)
    
    if [ "$current_commit" == "unknown" ]; then
        log_warn "无法获取 Git commit，跳过版本验证"
        return 0
    fi
    
    log_info "当前 Git commit: ${current_commit_short} (${current_commit})"
    
    # 检查已部署版本
    local deployed_commit=$(get_deployed_version)
    local deployed_commit_short=$(get_deployed_version_short)
    local deployed_time=$(get_deployed_build_time)
    
    if [ -n "$deployed_commit" ]; then
        if [ "$deployed_commit" == "$current_commit" ]; then
            log_info "✅ 镜像版本匹配: ${deployed_commit_short}"
            [ -n "$deployed_time" ] && log_info "   构建时间: ${deployed_time}"
        else
            log_warn "⚠️  镜像版本不匹配!"
            log_warn "   镜像版本: ${deployed_commit_short}"
            log_warn "   Git 版本: ${current_commit_short}"
            return 1
        fi
    else
        log_warn "未找到版本记录（首次构建或旧版本）"
    fi
    
    return 0
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
    local git_commit=$(get_git_commit)
    local git_commit_short=$(get_git_commit_short)
    local build_time=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    
    # 检查未提交的更改
    if ! check_git_clean; then
        log_warn "⚠️  检测到未提交的本地更改！"
        log_warn "   构建的镜像可能包含未提交的代码"
        echo ""
        read -p "是否继续构建？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "已取消构建，请先提交代码"
            exit 1
        fi
    fi
    
    log_info "Git commit: ${git_commit_short} (${git_commit})"
    log_info "构建时间: ${build_time}"
    
    # 使用 --no-cache 确保获取最新代码
    if [ "$1" == "--no-cache" ]; then
        log_info "无缓存构建..."
        DOCKER_BUILDKIT=1 docker compose -f "$compose_file" build --no-cache
    else
        DOCKER_BUILDKIT=1 docker compose -f "$compose_file" build
    fi
    
    # 保存构建版本信息到本地文件
    cat > "${PROJECT_DIR}/.deploy_version" << EOF
GIT_COMMIT=${git_commit}
GIT_COMMIT_SHORT=${git_commit_short}
BUILD_TIME=${build_time}
EOF
    
    log_info "镜像构建完成 (commit: ${git_commit_short})"
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
    
    # 验证镜像版本
    verify_image_version || {
        log_warn "镜像版本验证失败，建议使用 --no-cache 重新构建"
    }
    
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
    
    # 自动提交并推送更改
    auto_commit_push
    
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
    local no_cache=""
    if [ "$1" == "--no-cache" ]; then
        no_cache="--no-cache"
        log_step "🔄 开始强制更新（无缓存重建）"
    else
        log_step "🔄 开始快速更新"
    fi
    
    # 自动提交并推送更改
    auto_commit_push
    
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
    build_images $no_cache
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
    
    # 备份 PostgreSQL 数据库
    if docker ps --format '{{.Names}}' | grep -q "xhs-postgres"; then
        log_info "备份 PostgreSQL 数据库..."
        docker exec xhs-postgres pg_dump -U xhs -d xhs_data > "${backup_path}/xhs_data.sql" 2>/dev/null || {
            log_warn "PostgreSQL 数据库备份失败"
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
    
    # 恢复 PostgreSQL 数据库
    if [ -f "${backup_path}/xhs_data.sql" ]; then
        log_info "恢复 PostgreSQL 数据库..."
        docker exec -i xhs-postgres psql -U xhs -d xhs_data < "${backup_path}/xhs_data.sql"
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

# 验证镜像版本命令
cmd_verify() {
    log_step "🔍 验证代码版本"
    
    cd "$PROJECT_DIR"
    
    local current_commit=$(get_git_commit)
    local current_commit_short=$(get_git_commit_short)
    
    echo ""
    echo -e "${CYAN}=== Git 仓库状态 ===${NC}"
    
    if [ "$current_commit" == "unknown" ]; then
        log_warn "当前目录不是 Git 仓库"
    else
        echo "当前分支: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
        echo "最新提交: ${current_commit_short} (${current_commit})"
        echo "提交时间: $(git log -1 --format='%ci' 2>/dev/null || echo 'unknown')"
        echo "提交信息: $(git log -1 --format='%s' 2>/dev/null || echo 'unknown')"
        
        if ! check_git_clean; then
            echo ""
            echo -e "${YELLOW}⚠️  存在未提交的本地更改:${NC}"
            git status --short 2>/dev/null
        else
            echo -e "${GREEN}✅ 工作区干净${NC}"
        fi
    fi
    
    echo ""
    echo -e "${CYAN}=== 已部署镜像版本 ===${NC}"
    
    # 读取部署版本信息
    local deployed_commit=$(get_deployed_version)
    local deployed_commit_short=$(get_deployed_version_short)
    local deployed_time=$(get_deployed_build_time)
    
    echo ""
    if [ -n "$deployed_commit" ]; then
        echo "已部署版本: ${deployed_commit_short} (${deployed_commit})"
        [ -n "$deployed_time" ] && echo "构建时间: ${deployed_time}"
        
        if [ "$deployed_commit" == "$current_commit" ]; then
            echo -e "状态: ${GREEN}✅ 版本匹配${NC}"
        else
            echo -e "状态: ${RED}❌ 版本不匹配${NC}"
        fi
    else
        echo -e "状态: ${YELLOW}⚠️  未找到版本记录（首次部署或旧版本）${NC}"
    fi
    
    echo ""
    
    # 总结
    if [ -n "$deployed_commit" ]; then
        if [ "$deployed_commit" == "$current_commit" ]; then
            echo -e "${GREEN}========================================${NC}"
            echo -e "${GREEN}✅ 已部署镜像是最新 Git 提交的代码${NC}"
            echo -e "${GREEN}========================================${NC}"
        else
            echo -e "${YELLOW}========================================${NC}"
            echo -e "${YELLOW}⚠️  镜像版本与 Git 不一致${NC}"
            echo -e "${YELLOW}建议运行: ./auto-deploy.sh update --no-cache${NC}"
            echo -e "${YELLOW}========================================${NC}"
        fi
    else
        echo -e "${YELLOW}========================================${NC}"
        echo -e "${YELLOW}⚠️  无法确定已部署的版本${NC}"
        echo -e "${YELLOW}建议运行: ./auto-deploy.sh update --no-cache${NC}"
        echo -e "${YELLOW}========================================${NC}"
    fi
}

# ============================================================
# SSL 相关命令
# ============================================================

# 初始化 SSL 证书
cmd_ssl_init() {
    log_step "🔐 初始化 SSL 证书"
    
    check_docker
    check_env
    
    # 停止现有服务
    stop_services
    
    # 停止系统 Nginx
    stop_system_nginx
    
    # 创建 certbot 目录
    mkdir -p "${CERTBOT_DIR}/conf"
    mkdir -p "${CERTBOT_DIR}/www"
    
    log_info "域名: ${SSL_DOMAIN}"
    log_info "邮箱: ${SSL_EMAIL}"
    
    # 创建临时 nginx 配置用于证书验证
    log_info "创建临时 Nginx 配置..."
    
    cat > "${PROJECT_DIR}/nginx/nginx.temp.conf" << 'NGINX_TEMP'
server {
    listen 80;
    server_name _;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}
NGINX_TEMP
    
    # 创建临时 Dockerfile
    cat > "${PROJECT_DIR}/Dockerfile.temp" << 'DOCKERFILE_TEMP'
FROM nginx:alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx/nginx.temp.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
DOCKERFILE_TEMP
    
    # 构建并启动临时 nginx
    log_info "启动临时 Nginx 服务..."
    docker build -t xhs-temp-nginx -f Dockerfile.temp .
    docker run -d --name xhs-temp-nginx \
        -p 80:80 \
        -v "${CERTBOT_DIR}/www:/var/www/certbot" \
        xhs-temp-nginx
    
    sleep 3
    
    # 获取 SSL 证书
    log_info "获取 Let's Encrypt SSL 证书..."
    docker run --rm \
        -v "${CERTBOT_DIR}/conf:/etc/letsencrypt" \
        -v "${CERTBOT_DIR}/www:/var/www/certbot" \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "${SSL_EMAIL}" \
        --agree-tos \
        --no-eff-email \
        -d "${SSL_DOMAIN}"
    
    local cert_result=$?
    
    # 停止并删除临时容器
    log_info "清理临时资源..."
    docker stop xhs-temp-nginx 2>/dev/null || true
    docker rm xhs-temp-nginx 2>/dev/null || true
    docker rmi xhs-temp-nginx 2>/dev/null || true
    rm -f "${PROJECT_DIR}/nginx/nginx.temp.conf"
    rm -f "${PROJECT_DIR}/Dockerfile.temp"
    
    if [ $cert_result -eq 0 ]; then
        # 创建 SSL 模式标记文件
        touch "${PROJECT_DIR}/.ssl_mode"
        
        log_info "✅ SSL 证书获取成功！"
        log_info "证书位置: ${CERTBOT_DIR}/conf/live/${SSL_DOMAIN}/"
        
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}🔐 SSL 证书初始化成功！${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo "下一步: 运行以下命令启动带 SSL 的服务"
        echo "  ./auto-deploy.sh deploy"
        echo ""
        echo "访问地址: https://${SSL_DOMAIN}"
    else
        log_error "SSL 证书获取失败"
        log_info "请检查:"
        log_info "  1. 域名 ${SSL_DOMAIN} 是否正确解析到服务器"
        log_info "  2. 80 端口是否可从外部访问"
        log_info "  3. 防火墙是否已放行 80 端口"
        exit 1
    fi
}

# 启用 SSL 模式
cmd_ssl_enable() {
    log_step "🔐 启用 SSL 模式"
    
    # 检查证书是否存在
    if [ ! -d "${CERTBOT_DIR}/conf/live/${SSL_DOMAIN}" ]; then
        log_error "未找到 SSL 证书"
        log_info "请先运行: ./auto-deploy.sh ssl-init"
        exit 1
    fi
    
    # 创建 SSL 模式标记
    touch "${PROJECT_DIR}/.ssl_mode"
    
    log_info "✅ SSL 模式已启用"
    log_info "运行 ./auto-deploy.sh deploy 以应用更改"
}

# 禁用 SSL 模式
cmd_ssl_disable() {
    log_step "🔓 禁用 SSL 模式"
    
    rm -f "${PROJECT_DIR}/.ssl_mode"
    
    log_info "✅ SSL 模式已禁用，将使用 HTTP"
    log_info "运行 ./auto-deploy.sh deploy 以应用更改"
}

# 续期 SSL 证书
cmd_ssl_renew() {
    log_step "🔄 续期 SSL 证书"
    
    if [ ! -d "${CERTBOT_DIR}/conf/live/${SSL_DOMAIN}" ]; then
        log_error "未找到 SSL 证书"
        exit 1
    fi
    
    docker run --rm \
        -v "${CERTBOT_DIR}/conf:/etc/letsencrypt" \
        -v "${CERTBOT_DIR}/www:/var/www/certbot" \
        certbot/certbot renew
    
    # 重新加载 nginx
    if docker ps --format '{{.Names}}' | grep -q "xhs-frontend"; then
        log_info "重新加载 Nginx 配置..."
        docker exec xhs-frontend nginx -s reload
    fi
    
    log_info "✅ 证书续期完成"
}

# SSL 状态检查
cmd_ssl_status() {
    log_step "🔐 SSL 状态"
    
    echo ""
    if is_ssl_mode; then
        echo -e "${GREEN}SSL 模式: 已启用${NC}"
    else
        echo -e "${YELLOW}SSL 模式: 未启用${NC}"
    fi
    
    echo ""
    echo "证书目录: ${CERTBOT_DIR}/conf/live/${SSL_DOMAIN}/"
    
    if [ -d "${CERTBOT_DIR}/conf/live/${SSL_DOMAIN}" ]; then
        echo -e "${GREEN}证书状态: 已存在${NC}"
        
        # 显示证书过期时间
        local cert_file="${CERTBOT_DIR}/conf/live/${SSL_DOMAIN}/fullchain.pem"
        if [ -f "$cert_file" ]; then
            local expiry=$(openssl x509 -enddate -noout -in "$cert_file" 2>/dev/null | cut -d= -f2)
            echo "证书过期: $expiry"
        fi
    else
        echo -e "${YELLOW}证书状态: 未初始化${NC}"
        echo ""
        echo "运行以下命令初始化 SSL 证书:"
        echo "  ./auto-deploy.sh ssl-init"
    fi
    echo ""
}

# 显示帮助
show_help() {
    echo ""
    echo -e "${CYAN}🍓 小红书采集系统 - 自动化部署脚本${NC}"
    echo ""
    echo "使用方法: $0 [命令] [选项]"
    echo ""
    echo "基础命令:"
    echo -e "  ${GREEN}deploy${NC}       完整部署（停止旧服务 + 重新构建 + 启动）"
    echo "               选项: --no-cache  无缓存构建"
    echo -e "  ${GREEN}update${NC}       快速更新（拉取代码 + 备份 + 重新部署）"
    echo "               选项: --no-cache  强制无缓存重建镜像"
    echo -e "  ${GREEN}restart${NC}      重启所有服务"
    echo -e "  ${GREEN}stop${NC}         停止所有服务"
    echo -e "  ${GREEN}status${NC}       查看服务状态"
    echo -e "  ${GREEN}logs${NC}         查看实时日志"
    echo "               选项: [服务名]  只看特定服务（backend/frontend）"
    echo ""
    echo "SSL/HTTPS 命令:"
    echo -e "  ${GREEN}ssl-init${NC}     初始化 SSL 证书（首次启用 HTTPS 时使用）"
    echo -e "  ${GREEN}ssl-enable${NC}   启用 SSL 模式"
    echo -e "  ${GREEN}ssl-disable${NC}  禁用 SSL 模式（改用 HTTP）"
    echo -e "  ${GREEN}ssl-renew${NC}    手动续期 SSL 证书"
    echo -e "  ${GREEN}ssl-status${NC}   查看 SSL 状态"
    echo ""
    echo "其他命令:"
    echo -e "  ${GREEN}backup${NC}       备份数据"
    echo "               选项: --full  完整备份（含媒体文件）"
    echo -e "  ${GREEN}rollback${NC}     回滚到上一个版本"
    echo -e "  ${GREEN}verify${NC}       验证镜像代码版本是否与 Git 一致"
    echo -e "  ${GREEN}clean${NC}        清理无用的 Docker 资源"
    echo -e "  ${GREEN}clean-cache${NC}  清理 Python 缓存文件（__pycache__、.pyc 等）"
    echo -e "  ${GREEN}shell${NC}        进入后端容器"
    echo -e "  ${GREEN}help${NC}         显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 deploy              # 完整部署（HTTP 或 HTTPS，取决于 SSL 状态）"
    echo "  $0 deploy --no-cache   # 无缓存完整部署"
    echo "  $0 ssl-init            # 首次初始化 SSL 证书"
    echo "  $0 update              # 拉取代码并更新"
    echo "  $0 update --no-cache   # 拉取代码并强制重建镜像"
    echo "  $0 verify              # 检查镜像是否为最新 Git 代码"
    echo "  $0 logs backend        # 查看后端日志"
    echo ""
    echo "当前配置:"
    echo "  域名: ${SSL_DOMAIN}"
    if is_ssl_mode; then
        echo -e "  模式: ${GREEN}HTTPS (SSL)${NC}"
    else
        echo -e "  模式: ${YELLOW}HTTP${NC}"
    fi
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
            cmd_update "$2"
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
        verify)
            cmd_verify
            ;;
        clean-cache)
            log_step "🧹 清理 Python 缓存文件"
            clean_python_cache
            log_info "✅ 清理完成"
            ;;
        ssl-init)
            cmd_ssl_init
            ;;
        ssl-enable)
            cmd_ssl_enable
            ;;
        ssl-disable)
            cmd_ssl_disable
            ;;
        ssl-renew)
            cmd_ssl_renew
            ;;
        ssl-status)
            cmd_ssl_status
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


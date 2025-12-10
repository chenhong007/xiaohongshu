#!/bin/bash
# Nginx 代理初始化脚本
# 在服务器上首次部署时运行

set -e

echo "🚀 初始化 Nginx 代理..."

# 创建共享网络
if ! docker network inspect nginx-proxy >/dev/null 2>&1; then
    echo "创建 nginx-proxy 网络..."
    docker network create nginx-proxy
else
    echo "nginx-proxy 网络已存在"
fi

# 创建必要目录
mkdir -p certs certbot/conf certbot/www

# 生成默认自签名证书（用于处理未知域名的 HTTPS 请求）
if [ ! -f "certs/default.crt" ]; then
    echo "生成默认 SSL 证书..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout certs/default.key \
        -out certs/default.crt \
        -subj "/CN=default"
fi

# 启动 Nginx 代理
echo "启动 Nginx 代理..."
docker compose up -d

echo ""
echo "✅ Nginx 代理初始化完成！"
echo ""
echo "现在可以部署各个项目了。"
echo "每个项目只需要加入 nginx-proxy 网络即可。"
echo ""
echo "添加新站点："
echo "1. 在 conf.d/ 目录创建新的配置文件"
echo "2. 运行: docker compose exec nginx-proxy nginx -s reload"


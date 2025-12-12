# 后端 Flask 应用 Dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PYTHONPATH=/app:/app/Spider_XHS

# 安装系统依赖（用于 PyExecJS）
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p datas/media_datas datas/excel_datas

# 创建 static 目录软链接，解决 Spider_XHS/xhs_utils/xhs_util.py 中相对路径问题
# xhs_util.py 会尝试 ../static/xhs_xs_xsc_56.js 或 static/xhs_xs_xsc_56.js
RUN ln -sf /app/Spider_XHS/static /app/static

# 暴露端口
EXPOSE 8000

# 使用 gunicorn 启动应用
# 【性能优化】使用 gthread worker 支持多线程并发
# - workers: 进程数（建议 CPU 核数 * 2 + 1）
# - threads: 每个进程的线程数
# - timeout: 请求超时时间
# - worker-class: 使用 gthread 支持多线程处理请求
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "run:app"]


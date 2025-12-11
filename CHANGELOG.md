# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2025-12-11

### Added
- 笔记封面缓存与预览：新增 `cover_remote/cover_local` 字段，封面缓存至 `datas/media_datas`，通过 `/api/media/<filename>` 提供访问，下载页支持缩略图预览与远程链接跳转
- 深度同步防爬延迟配置：新增 `DEEP_SYNC_DELAY_MIN/DEEP_SYNC_DELAY_MAX/DEEP_SYNC_EXTRA_PAUSE_CHANCE/DEEP_SYNC_EXTRA_PAUSE_MAX` 环境变量控制随机延时
- 应用启动自动创建媒体与导出目录，减少手工准备

### Changed
- 深度同步请求新增随机抖动与偶发长暂停；用户笔记列表请求增加随机延迟，降低封禁风险
- Cookie 认证失败时会批量标记剩余账号失败，避免前端卡在“准备中”

### Fixed
- Cookie 运行时长结算在先置 `is_valid=False` 的场景下仍会正确完成

## [1.2.0] - 2025-12-10

### Added
- **Cookie 安全增强**
  - 新增 Cookie 加密存储功能，使用 Fernet 对称加密
  - 新增 Cookie 传输加密，支持前后端加密通信
  - 新增 Cookie 运行时长统计（开始时间、累计运行时长）
  - 新增 Cookie 失效时记录上次有效运行时长
  - 新增 Cookie 历史记录功能，优先使用最近有效的 Cookie
  
- **Docker 部署支持**
  - 新增 Docker 容器化部署配置
  - 新增 docker-compose.yml 基础部署配置
  - 新增 docker-compose.ssl.yml SSL 部署配置
  - 新增 `auto-deploy.sh` 自动化部署脚本
  - 支持一键部署、更新、回滚、备份等操作
  
- **SSL/HTTPS 支持**
  - 集成 Let's Encrypt 自动证书申请
  - 支持 SSL 证书自动续期
  - 新增 Nginx SSL 配置模板

- **数据库增强**
  - 新增 `migrate_db.py` 数据库迁移工具
  - Cookie 模型新增加密字段和运行时长字段

### Changed
- 优化项目目录结构
- 改进 API 错误处理和响应格式
- 前端优化 Cookie 状态显示

### Security
- Cookie 存储从明文改为加密存储
- 前后端 Cookie 传输加密
- 新增 `crypto.py` 加密工具模块

## [1.1.0] - 2025-11-01

### Added
- **搜索功能**
  - 新增小红书用户搜索 API
  - 新增小红书笔记搜索 API
  - 支持从搜索结果添加博主

- **批量操作**
  - 支持批量同步博主笔记
  - 支持批量删除博主和笔记
  - 支持博主账号批量导入/导出

- **笔记下载**
  - 支持按条件筛选笔记
  - 支持笔记数据导出为 JSON

## [1.0.0] - 2025-10-01

### Added
- 初始化项目结构
- 添加 React + Vite 基础配置
- 添加 Tailwind CSS 配置
- 添加基础组件:
  - Sidebar (侧边栏)
  - ContentArea (内容区域)
  - DownloadPage (下载页面)
  - UserLogin (用户登录)
- 创建 README.md 和 CHANGELOG.md 文件
- 后端 Flask 应用框架搭建
- SQLite 数据库集成
- 博主管理 API
- 笔记采集功能
- Cookie 管理功能


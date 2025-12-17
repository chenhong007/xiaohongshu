# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **全局 API 调用限流器**
  - 新增 `rate_limiter.py` 模块，实现令牌桶算法的全局请求限流
  - 新增 `TokenBucketRateLimiter` 类，提供平滑的请求速率控制
  - 新增 `RateLimitedXHSApis` 包装类，透明代理原始 API 并自动限流
  - 支持动态速率调整：检测到限流响应后自动降速，连续成功后逐步恢复
  - 支持突发请求容忍（burst_size），避免过于严格的限制
  - 支持限流惩罚机制，触发限流后进入惩罚期
  - 提供 `get_api_rate_limiter()` 全局单例和统计信息查询
  - 默认配置：每2秒1个请求，突发容量3个，限流后惩罚60秒

### Changed
- **xsec_token 获取逻辑优化**
  - 移除冗余的「通过搜索用户昵称获取 xsec_token」备选方案
  - 笔记详情的 xsec_token 统一从用户笔记列表接口 `/api/sns/web/v1/user_posted` 返回数据中获取
  - 简化 `XsecTokenManager.refresh_user_token()` 方法，仅保留 homefeed 获取策略
  
- **API 调用架构优化**
  - `sync_service.py` 改为使用 `RateLimitedXHSApis` 替代直接调用 `XHS_Apis`
  - `cookie_service.py` 验证接口使用全局限流器
  - `search.py` 搜索接口使用全局限流器
  - 移除各模块分散的延迟管理逻辑，统一由限流器控制请求速率

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


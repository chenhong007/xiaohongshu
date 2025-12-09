# Xiaohongshu Frontend

这是一个基于 React 和 Vite 构建的小红书数据交互/下载器前端项目。

## 功能特性

- **现代技术栈**: 使用 React, Vite, Tailwind CSS 构建。
- **组件化设计**: 包含侧边栏 (`Sidebar`)、内容区域 (`ContentArea`) 和下载页面 (`DownloadPage`) 等组件。
- **响应式布局**: 使用 Tailwind CSS 实现灵活的界面设计。

## 目录结构

- `src/`: 源代码目录
  - `components/`: React 组件
  - `App.jsx`: 主应用组件
  - `main.jsx`: 入口文件
- `backend/`: 后端相关代码 (Python)
- `Spider_XHS/`: 小红书爬虫模块
- `XHS-Downloader/`: 小红书下载器模块

## 快速开始

### 前置要求

- Node.js (推荐 v16+)
- npm 或 yarn

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

### 构建生产版本

```bash
npm run build
```

### 预览生产构建

```bash
npm run preview
```

## 贡献

欢迎提交 Issue 和 Pull Request。

## 许可证

[MIT](LICENSE)


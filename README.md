# 小红书采集系统

一个用于采集和管理小红书博主笔记数据的全栈应用，基于 React + Flask 构建。

## ✨ 功能特性

- **博主管理**: 添加、删除、批量导入/导出博主账号
- **笔记采集**: 自动采集博主的所有笔记数据
- **笔记下载**: 支持筛选、搜索、排序和导出笔记
- **Cookie 管理**: 支持手动添加小红书 Cookie
- **实时进度**: 采集任务实时进度显示

## 🏗️ 项目架构

```
xiaohongshu/
├── backend/                    # 后端服务 (Flask)
│   ├── app/                    # Flask 应用包
│   │   ├── __init__.py         # 应用工厂
│   │   ├── config.py           # 配置管理
│   │   ├── extensions.py       # Flask 扩展
│   │   ├── api/                # API 蓝图
│   │   │   ├── accounts.py     # 账号管理 API
│   │   │   ├── auth.py         # 认证相关 API
│   │   │   ├── notes.py        # 笔记管理 API
│   │   │   └── search.py       # 搜索 API
│   │   ├── models/             # 数据模型 (SQLAlchemy)
│   │   │   ├── account.py      # Account 模型
│   │   │   ├── note.py         # Note 模型
│   │   │   └── cookie.py       # Cookie 模型
│   │   └── services/           # 业务服务层
│   │       └── sync_service.py # 笔记同步服务
│   ├── apis/                   # 小红书 API 封装
│   ├── xhs_utils/              # 工具函数
│   ├── static/                 # 静态资源 (JS 签名等)
│   ├── datas/                  # 数据存储目录
│   ├── run.py                  # 后端入口文件
│   ├── requirements.txt        # Python 依赖
│   └── xhs_data.db             # SQLite 数据库
│
├── src/                        # 前端源码 (React)
│   ├── components/             # React 组件
│   │   ├── Sidebar.jsx         # 侧边栏导航
│   │   ├── ContentArea.jsx     # 博主管理页面
│   │   ├── DownloadPage.jsx    # 笔记下载页面
│   │   └── UserLogin.jsx       # 用户登录组件
│   ├── services/               # API 服务层
│   │   ├── api.js              # 统一 API 请求封装
│   │   └── index.js            # 服务导出
│   ├── App.jsx                 # 主应用组件
│   ├── main.jsx                # 入口文件
│   └── index.css               # 全局样式
│
├── index.html                  # HTML 入口
├── package.json                # Node.js 依赖
├── vite.config.js              # Vite 配置
├── tailwind.config.js          # Tailwind CSS 配置
└── start_app.bat               # Windows 一键启动脚本
```

## 🛠️ 技术栈

### 前端
- **React 18** - UI 框架
- **Vite** - 构建工具
- **Tailwind CSS** - 样式框架
- **Lucide React** - 图标库

### 后端
- **Flask** - Web 框架
- **Flask-SQLAlchemy** - ORM
- **Flask-CORS** - 跨域支持
- **SQLite** - 数据库
- **PyExecJS** - JS 执行引擎

## 🚀 快速开始

### 前置要求

- **Node.js** >= 16.0
- **Python** >= 3.8
- **npm** 或 **yarn**

### 方式一：一键启动 (Windows)

```bash
# 双击运行启动脚本
start_app.bat
```

### 方式二：手动启动

#### 1. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

#### 2. 安装前端依赖

```bash
npm install
```

#### 3. 启动后端服务

```bash
cd backend
python run.py
```

后端服务将在 http://localhost:8000 启动

#### 4. 启动前端服务

```bash
npm run dev
```

前端服务将在 http://localhost:5173 启动

### 构建生产版本

```bash
npm run build
```

## 📡 API 接口

### 账号管理
| 方法 | 路径 | 说明 |
|-----|------|-----|
| GET | `/api/accounts` | 获取账号列表 |
| POST | `/api/accounts` | 添加账号 |
| DELETE | `/api/accounts/:id` | 删除账号 |
| POST | `/api/accounts/:id/sync` | 同步单个账号 |
| POST | `/api/accounts/sync-all` | 同步所有账号 |
| POST | `/api/accounts/sync-batch` | 批量同步账号 |
| POST | `/api/accounts/batch-delete` | 批量删除账号 |

### 笔记管理
| 方法 | 路径 | 说明 |
|-----|------|-----|
| GET | `/api/notes` | 获取笔记列表 (支持筛选/分页) |
| GET | `/api/notes/:id` | 获取笔记详情 |
| DELETE | `/api/notes/:id` | 删除笔记 |
| POST | `/api/notes/batch-delete` | 批量删除笔记 |
| POST | `/api/notes/export` | 导出笔记数据 |
| GET | `/api/notes/stats` | 获取统计信息 |

### 认证相关
| 方法 | 路径 | 说明 |
|-----|------|-----|
| GET | `/api/user/me` | 获取当前用户信息 |
| POST | `/api/login` | 登录 |
| POST | `/api/logout` | 登出 |
| POST | `/api/cookie/manual` | 手动设置 Cookie |
| POST | `/api/cookie/check` | 检查 Cookie 有效性 |

### 搜索相关
| 方法 | 路径 | 说明 |
|-----|------|-----|
| GET | `/api/search/users` | 搜索小红书用户 |
| GET | `/api/search/notes` | 搜索小红书笔记 |

## ⚙️ 配置说明

### 环境变量

在 `backend/` 目录下创建 `.env` 文件：

```env
# 小红书 Cookie (可选，也可在界面中手动添加)
COOKIES=你的小红书cookie字符串

# Flask 密钥 (生产环境请修改)
SECRET_KEY=your-secret-key
```

### Cookie 获取方式

1. 登录 [小红书网页版](https://www.xiaohongshu.com)
2. 打开浏览器开发者工具 (F12)
3. 切换到 Network 标签
4. 刷新页面，找到任意请求
5. 复制请求头中的 `Cookie` 值

## 📝 使用说明

### 添加博主

1. 点击「博主管理」页面的「添加」按钮
2. 在搜索框中输入博主名称
3. 从搜索结果中点击选择要添加的博主

### 采集笔记

1. 在博主列表中勾选要采集的博主
2. 点击「同步选中」或「同步全部」按钮
3. 等待采集完成，可在进度条中查看进度

### 下载/导出笔记

1. 切换到「笔记下载」页面
2. 使用筛选条件筛选笔记
3. 勾选要导出的笔记
4. 点击「导出」按钮下载 JSON 文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 📄 许可证

[MIT](LICENSE)

## ⚠️ 免责声明

本项目仅供学习和研究使用，请勿用于商业用途。使用本工具时请遵守小红书的服务条款和相关法律法规。

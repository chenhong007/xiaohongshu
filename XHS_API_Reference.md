# 小红书 API 参考文档

本文档整理自 `Spider_XHS` 和 `XHS-Downloader` 项目，主要包含 PC 端 Web API 和创作者中心 API 的接口定义与使用说明。

> **注意**: 本文档中的接口均为非官方 API，基于逆向分析整理，仅供学习研究使用。

## 1. PC 端 Web API (`XHS_Apis`)

**类名**: `XHS_Apis`
**源文件**: `Spider_XHS/apis/xhs_pc_apis.py`
**基础 URL**: `https://edith.xiaohongshu.com`

### 1.1 首页推荐与频道

#### 获取主页所有频道
- **方法**: `get_homefeed_all_channel`
- **API**: `/api/sns/web/v1/homefeed/category`
- **请求方式**: GET
- **参数**:
    - `cookies_str`: Cookie 字符串
    - `proxies`: 代理配置 (可选)
- **描述**: 获取小红书首页的分类频道列表。

#### 获取主页推荐笔记
- **方法**: `get_homefeed_recommend`
- **API**: `/api/sns/web/v1/homefeed`
- **请求方式**: POST
- **参数**:
    - `category`: 频道 ID (例如: `homefeed_recommend`)
    - `cursor_score`: 分页游标 (字符串)
    - `refresh_type`: 刷新类型 (整数)
    - `note_index`: 笔记索引 (整数)
    - `cookies_str`: Cookie 字符串
- **描述**: 获取指定频道的推荐笔记流数据。

#### 根据数量获取主页推荐
- **方法**: `get_homefeed_recommend_by_num`
- **描述**: 封装方法，循环调用 `get_homefeed_recommend` 直到获取指定数量的笔记。

### 1.2 用户信息

#### 获取其他用户信息
- **方法**: `get_user_info`
- **API**: `/api/sns/web/v1/user/otherinfo`
- **请求方式**: GET
- **参数**:
    - `user_id`: 目标用户 ID
    - `cookies_str`: Cookie 字符串
- **描述**: 获取指定用户的公开基本信息。

#### 获取当前用户信息 (Self)
- **方法**: `get_user_self_info` / `get_user_self_info2`
- **API**: 
    - `/api/sns/web/v1/user/selfinfo`
    - `/api/sns/web/v2/user/me`
- **请求方式**: GET
- **参数**: `cookies_str`
- **描述**: 获取当前登录用户的详细信息。

### 1.3 用户笔记与收藏

#### 获取用户笔记 (分页)
- **方法**: `get_user_note_info`
- **API**: `/api/sns/web/v1/user_posted`
- **请求方式**: GET
- **参数**:
    - `user_id`: 用户 ID
    - `cursor`: 分页游标
    - `cookies_str`: Cookie 字符串
    - `xsec_token`: 安全 Token (通常从 URL 获取)
    - `xsec_source`: 来源标识 (默认 `pc_search`)
- **描述**: 获取指定用户发布的笔记列表。

#### 获取用户所有笔记 (封装)
- **方法**: `get_user_all_notes`
- **参数**: `user_url` (包含 `user_id` 和 `xsec_token` 的完整 URL), `cookies_str`
- **描述**: 自动处理分页，获取用户所有笔记。

#### 获取用户点赞的笔记
- **方法**: `get_user_like_note_info` / `get_user_all_like_note_info`
- **API**: `/api/sns/web/v1/note/like/page`
- **请求方式**: GET
- **描述**: 获取用户点赞过的笔记列表。

#### 获取用户收藏的笔记
- **方法**: `get_user_collect_note_info` / `get_user_all_collect_note_info`
- **API**: `/api/sns/web/v2/note/collect/page`
- **请求方式**: GET
- **描述**: 获取用户收藏夹中的笔记列表。

### 1.4 笔记详情与搜索

#### 获取笔记详情
- **方法**: `get_note_info`
- **API**: `/api/sns/web/v1/feed`
- **请求方式**: POST
- **参数**:
    - `url`: 笔记完整 URL
    - `cookies_str`: Cookie 字符串
- **数据包**: 包含 `source_note_id`, `xsec_token`, `xsec_source` 等。
- **描述**: 获取单篇笔记的详细内容（图片、视频地址、文案等）。

#### 获取搜索关键词推荐
- **方法**: `get_search_keyword`
- **API**: `/api/sns/web/v1/search/recommend`
- **请求方式**: GET
- **参数**: `word` (关键词)
- **描述**: 获取搜索建议/联想词。

#### 搜索笔记
- **方法**: `search_note` / `search_some_note`
- **API**: `/api/sns/web/v1/search/notes`
- **请求方式**: POST
- **参数**:
    - `query`: 搜索关键词
    - `sort_type_choice`: 排序 (0综合, 1最新, 2最热, 3评论最多, 4收藏最多)
    - `note_type`: 类型 (0不限, 1视频, 2图文)
    - `note_time`: 时间范围 (0不限, 1一天内, 2一周内, 3半年内)
- **描述**: 执行关键词搜索并返回笔记结果。

#### 搜索用户
- **方法**: `search_user` / `search_some_user`
- **API**: `/api/sns/web/v1/search/usersearch`
- **请求方式**: POST
- **描述**: 搜索小红书用户。

### 1.5 评论与消息互动

#### 获取笔记一级评论
- **方法**: `get_note_out_comment`
- **API**: `/api/sns/web/v2/comment/page`
- **请求方式**: GET
- **参数**: `note_id`, `cursor`, `xsec_token`
- **描述**: 获取笔记下的主评论列表。

#### 获取笔记二级评论 (子评论)
- **方法**: `get_note_inner_comment`
- **API**: `/api/sns/web/v2/comment/sub/page`
- **请求方式**: GET
- **参数**: `comment` (父评论对象), `cursor`
- **描述**: 获取某条评论下的回复列表。

#### 获取未读消息数量
- **方法**: `get_unread_message`
- **API**: `/api/sns/web/unread_count`
- **请求方式**: GET

#### 获取消息通知
- **方法**: `get_metions` (提及/评论), `get_likesAndcollects` (赞藏), `get_new_connections` (新增关注)
- **API**: 
    - `/api/sns/web/v1/you/mentions`
    - `/api/sns/web/v1/you/likes`
    - `/api/sns/web/v1/you/connections`
- **请求方式**: GET

### 1.6 工具方法 (静态方法)

- **`get_note_no_water_video(note_id)`**: 解析笔记页面 HTML meta 标签，提取无水印视频地址。
- **`get_note_no_water_img(img_url)`**: 通过替换 URL 域名 (`sns-img-qc.xhscdn.com`) 获取无水印图片。

---

## 2. 创作者中心 API (`XHS_Creator_Apis`)

**类名**: `XHS_Creator_Apis`
**源文件**: `Spider_XHS/apis/xhs_creator_apis.py`
**基础 URL**: `https://edith.xiaohongshu.com`

#### 获取已发布笔记列表
- **方法**: `get_publish_note_info`
- **API**: `/web_api/sns/v5/creator/note/user/posted`
- **请求方式**: GET
- **参数**:
    - `page`: 页码
    - `cookies_str`: Cookie 字符串
- **Header**: 需要 `x-s`, `x-t` (X-Bogus/Signature) 签名参数。
- **描述**: 获取创作者后台的已发布笔记数据。

#### 获取所有发布笔记
- **方法**: `get_all_publish_note_info`
- **描述**: 循环调用 `get_publish_note_info` 获取全量列表。

---

## 3. XHS-Downloader 数据解析与下载

**源文件**: `XHS-Downloader/source/`

### 3.1 数据字段解析 (`Explore` 类)
**文件**: `source/application/explore.py`

解析 JSON 数据中的关键字段：
- **互动数据**: `interactInfo` (收藏、评论、分享、点赞)
- **标签**: `tagList`
- **基本信息**: `noteId`, `title`, `desc`, `type` (video/normal)
- **时间**: `time` (发布时间), `lastUpdateTime`
- **用户信息**: `user.nickname`, `user.userId`

### 3.2 资源下载 (`Download` 类)
**文件**: `source/application/download.py`

- **图片格式支持**: `png`, `jpeg`, `webp`, `avif`, `heic`
- **视频格式支持**: `mp4`, `mov`
- **功能**:
    - 自动重试与断点续传 (Range 请求)
    - 自动检测文件类型 (Magic Bytes)
    - 文件夹归档 (按作者/作品)


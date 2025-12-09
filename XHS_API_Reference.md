# 小红书 API 参考文档

本文档整理自当前项目代码，主要包含 PC 端 Web API (`XHS_Apis`) 和创作者中心 API (`XHS_Creator_Apis`) 的接口定义与使用说明。

> **注意**: 本文档中的接口均为非官方 API，基于逆向分析整理，仅供学习研究使用。

## 1. PC 端 Web API (`XHS_Apis`)

**类名**: `XHS_Apis`
**源文件**: `backend/apis/xhs_pc_apis.py`
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
    - `category`: 频道 ID
    - `cursor_score`: 分页游标
    - `refresh_type`: 刷新类型
    - `note_index`: 笔记索引
    - `cookies_str`: Cookie 字符串
    - `proxies`: 代理配置 (可选)
- **描述**: 获取指定频道的推荐笔记流数据。

#### 根据数量获取主页推荐 (封装)
- **方法**: `get_homefeed_recommend_by_num`
- **参数**:
    - `category`: 频道 ID
    - `require_num`: 需要获取的笔记数量
    - `cookies_str`: Cookie 字符串
    - `proxies`: 代理配置 (可选)
- **描述**: 循环调用 `get_homefeed_recommend` 直到获取指定数量的笔记。

### 1.2 用户信息

#### 获取其他用户信息
- **方法**: `get_user_info`
- **API**: `/api/sns/web/v1/user/otherinfo`
- **请求方式**: GET
- **参数**:
    - `user_id`: 目标用户 ID
    - `cookies_str`: Cookie 字符串
    - `proxies`: 代理配置 (可选)
- **描述**: 获取指定用户的公开基本信息。

#### 获取当前用户信息 (Self)
- **方法**: `get_user_self_info` / `get_user_self_info2`
- **API**: 
    - `/api/sns/web/v1/user/selfinfo`
    - `/api/sns/web/v2/user/me`
- **请求方式**: GET
- **参数**: `cookies_str`, `proxies` (可选)
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
    - `xsec_token`: 安全 Token
    - `xsec_source`: 来源标识
    - `proxies`: 代理配置 (可选)
- **描述**: 获取指定用户发布的笔记列表。

#### 获取用户所有笔记 (封装)
- **方法**: `get_user_all_notes`
- **参数**: `user_url` (包含 `user_id` 等信息的完整 URL), `cookies_str`, `proxies` (可选)
- **描述**: 自动从 URL 解析 `user_id`, `xsec_token`, `xsec_source` 并处理分页，获取用户所有笔记。

#### 获取用户点赞的笔记
- **方法**: `get_user_like_note_info`
- **API**: `/api/sns/web/v1/note/like/page`
- **请求方式**: GET
- **参数**: `user_id`, `cursor`, `cookies_str`, `xsec_token`, `xsec_source`, `proxies` (可选)
- **描述**: 获取用户点赞过的笔记列表 (分页)。

#### 获取用户所有点赞笔记 (封装)
- **方法**: `get_user_all_like_note_info`
- **参数**: `user_url`, `cookies_str`, `proxies` (可选)
- **描述**: 获取用户所有点赞过的笔记。

#### 获取用户收藏的笔记
- **方法**: `get_user_collect_note_info`
- **API**: `/api/sns/web/v2/note/collect/page`
- **请求方式**: GET
- **参数**: `user_id`, `cursor`, `cookies_str`, `xsec_token`, `xsec_source`, `proxies` (可选)
- **描述**: 获取用户收藏夹中的笔记列表 (分页)。

#### 获取用户所有收藏笔记 (封装)
- **方法**: `get_user_all_collect_note_info`
- **参数**: `user_url`, `cookies_str`, `proxies` (可选)
- **描述**: 获取用户所有收藏的笔记。

### 1.4 笔记详情与搜索

#### 获取笔记详情
- **方法**: `get_note_info`
- **API**: `/api/sns/web/v1/feed`
- **请求方式**: POST
- **参数**:
    - `url`: 笔记完整 URL (用于解析 `note_id`, `xsec_token`)
    - `cookies_str`: Cookie 字符串
    - `proxies`: 代理配置 (可选)
- **描述**: 获取单篇笔记的详细内容。

#### 获取搜索关键词推荐
- **方法**: `get_search_keyword`
- **API**: `/api/sns/web/v1/search/recommend`
- **请求方式**: GET
- **参数**: `word` (关键词), `cookies_str`, `proxies` (可选)
- **描述**: 获取搜索建议/联想词。

#### 搜索笔记
- **方法**: `search_note`
- **API**: `/api/sns/web/v1/search/notes`
- **请求方式**: POST
- **参数**:
    - `query`: 搜索关键词
    - `cookies_str`: Cookie 字符串
    - `page`: 页码 (默认 1)
    - `sort_type_choice`: 排序 (0综合, 1最新, 2最热, 3评论最多, 4收藏最多)
    - `note_type`: 类型 (0不限, 1视频, 2图文)
    - `note_time`: 时间范围 (0不限, 1一天内, 2一周内, 3半年内)
    - `note_range`: 笔记范围 (0不限, 1已看过, 2未看过, 3已关注)
    - `pos_distance`: 位置距离 (0不限, 1同城, 2附近)
    - `geo`: 定位信息 (JSON 字符串)
    - `proxies`: 代理配置 (可选)
- **描述**: 执行关键词搜索并返回笔记结果。

#### 指定数量搜索笔记 (封装)
- **方法**: `search_some_note`
- **参数**: `query`, `require_num`, `cookies_str`, `sort_type_choice`, `note_type`, `note_time`, `note_range`, `pos_distance`, `geo`, `proxies` (可选)
- **描述**: 循环调用 `search_note` 获取指定数量的搜索结果。

#### 搜索用户
- **方法**: `search_user`
- **API**: `/api/sns/web/v1/search/usersearch`
- **请求方式**: POST
- **参数**: `query`, `cookies_str`, `page`, `proxies` (可选)
- **描述**: 搜索小红书用户。

#### 指定数量搜索用户 (封装)
- **方法**: `search_some_user`
- **参数**: `query`, `require_num`, `cookies_str`, `proxies` (可选)
- **描述**: 循环调用 `search_user` 获取指定数量的用户搜索结果。

### 1.5 评论与消息互动

#### 获取笔记一级评论
- **方法**: `get_note_out_comment`
- **API**: `/api/sns/web/v2/comment/page`
- **请求方式**: GET
- **参数**: `note_id`, `cursor`, `xsec_token`, `cookies_str`, `proxies` (可选)
- **描述**: 获取笔记下的主评论列表。

#### 获取笔记全部一级评论 (封装)
- **方法**: `get_note_all_out_comment`
- **参数**: `note_id`, `xsec_token`, `cookies_str`, `proxies` (可选)
- **描述**: 获取笔记的所有一级评论。

#### 获取笔记二级评论 (子评论)
- **方法**: `get_note_inner_comment`
- **API**: `/api/sns/web/v2/comment/sub/page`
- **请求方式**: GET
- **参数**: `comment` (父评论对象), `cursor`, `xsec_token`, `cookies_str`, `proxies` (可选)
- **描述**: 获取某条评论下的回复列表。

#### 获取笔记全部二级评论 (封装)
- **方法**: `get_note_all_inner_comment`
- **参数**: `comment`, `xsec_token`, `cookies_str`, `proxies` (可选)
- **描述**: 获取某条评论下的所有回复。

#### 获取笔记所有评论 (封装)
- **方法**: `get_note_all_comment`
- **参数**: `url` (笔记 URL), `cookies_str`, `proxies` (可选)
- **描述**: 获取笔记的所有评论（包含一级和二级）。

#### 获取未读消息数量
- **方法**: `get_unread_message`
- **API**: `/api/sns/web/unread_count`
- **请求方式**: GET
- **参数**: `cookies_str`, `proxies` (可选)

#### 获取评论和@提醒
- **方法**: `get_metions`
- **API**: `/api/sns/web/v1/you/mentions`
- **请求方式**: GET
- **参数**: `cursor`, `cookies_str`, `proxies` (可选)

#### 获取全部评论和@提醒 (封装)
- **方法**: `get_all_metions`
- **参数**: `cookies_str`, `proxies` (可选)

#### 获取赞和收藏通知
- **方法**: `get_likesAndcollects`
- **API**: `/api/sns/web/v1/you/likes`
- **请求方式**: GET
- **参数**: `cursor`, `cookies_str`, `proxies` (可选)

#### 获取全部赞和收藏通知 (封装)
- **方法**: `get_all_likesAndcollects`
- **参数**: `cookies_str`, `proxies` (可选)

#### 获取新增关注
- **方法**: `get_new_connections`
- **API**: `/api/sns/web/v1/you/connections`
- **请求方式**: GET
- **参数**: `cursor`, `cookies_str`, `proxies` (可选)

#### 获取全部新增关注 (封装)
- **方法**: `get_all_new_connections`
- **参数**: `cookies_str`, `proxies` (可选)

### 1.6 工具方法 (静态方法)

- **`get_note_no_water_video(note_id)`**: 解析笔记页面 HTML meta 标签，提取无水印视频地址。
- **`get_note_no_water_img(img_url)`**: 通过替换 URL 域名 (`sns-img-qc.xhscdn.com` 等) 获取无水印图片。

---

## 2. 创作者中心 API (`XHS_Creator_Apis`)

**类名**: `XHS_Creator_Apis`
**源文件**: `backend/apis/xhs_creator_apis.py`
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

#### 获取所有发布笔记 (封装)
- **方法**: `get_all_publish_note_info`
- **参数**: `cookies_str`
- **描述**: 循环调用 `get_publish_note_info` 获取全量列表。

# 小红书 API 接口与功能实现整理

基于 `@XHS-Downloader` 和 `@Spider_XHS` 项目的分析，以下是整理的小红书相关 API 接口及核心功能实现方案。

## 1. 核心 API 接口列表

接口主要来源于 `Spider_XHS/apis/xhs_pc_apis.py`，基于 Web 端（PC版）逆向。

**基础信息：**
*   **Base URL**: `https://edith.xiaohongshu.com`
*   **必要参数**:
    *   `cookies_str` (Header: `Cookie`): 必须包含有效的 `web_session`。
    *   `xsec_token`: 某些列表接口返回的安全令牌，用于获取详情。

| 功能分类 | 接口名称 | API 路径 | 请求方式 | 核心参数 |
| :--- | :--- | :--- | :--- | :--- |
| **博主信息** | 获取指定用户信息 | `/api/sns/web/v1/user/otherinfo` | GET | `target_user_id` |
| **博主笔记** | 获取用户笔记列表 | `/api/sns/web/v1/user_posted` | GET | `user_id`, `cursor`, `num` |
| **博主收藏** | 获取用户收藏笔记 | `/api/sns/web/v2/note/collect/page` | GET | `user_id`, `cursor` |
| **博主点赞** | 获取用户点赞笔记 | `/api/sns/web/v1/note/like/page` | GET | `user_id`, `cursor` |
| **笔记详情** | 获取单篇笔记详情 | `/api/sns/web/v1/feed` | POST | `source_note_id`, `xsec_token` |
| **搜索笔记** | 关键词搜索笔记 | `/api/sns/web/v1/search/notes` | POST | `keyword`, `page`, `sort` (排序) |
| **搜索用户** | 关键词搜索博主 | `/api/sns/web/v1/search/usersearch` | POST | `keyword`, `page` |
| **一级评论** | 获取笔记一级评论 | `/api/sns/web/v2/comment/page` | GET | `note_id`, `cursor`, `xsec_token` |
| **二级评论** | 获取子评论(回复) | `/api/sns/web/v2/comment/sub/page` | GET | `root_comment_id`, `note_id` |
| **首页推荐** | 获取首页Feed流 | `/api/sns/web/v1/homefeed` | POST | `category` (频道), `refresh_type` |

---

## 2. 核心功能代码实现示例

### 场景一：采集博主的所有内容

逻辑：通过 `user_id` 循环分页获取所有笔记列表。

```python
# 参考: Spider_XHS/apis/xhs_pc_apis.py -> get_user_all_notes

def get_user_all_notes(self, user_url):
    """
    爬取一个用户的所有笔记
    """
    # 1. 从 URL 解析 user_id (例如: https://www.xiaohongshu.com/user/profile/64c3f392000000002b009e45)
    
    note_list = []
    cursor = ''
    while True:
        # 2. 调用 API 获取一页数据
        # API: /api/sns/web/v1/user_posted
        params = {
            "num": "30",
            "cursor": cursor,
            "user_id": user_id,
        }
        # 发送请求 (需带上 headers 和 cookies)...
        res = requests.get(base_url + api, params=params, ...)
        
        # 3. 提取笔记数据
        if "notes" in res["data"]:
            notes = res["data"]["notes"]
            note_list.extend(notes)
        
        # 4. 处理分页
        if not res["data"].get("has_more"):
            break
        cursor = res["data"]["cursor"]
        
    return note_list
```

### 场景二：对指定内容（视频/图片）的下载

逻辑：解析笔记详情数据，提取无水印链接并下载。

#### 1. 数据解析 (提取下载链接)

参考: `XHS-Downloader/source/application/explore.py`

```python
def extract_media_info(data):
    """
    从笔记详情 JSON 中提取媒体链接
    """
    result = {}
    result["title"] = data.get("title")
    type_ = data.get("type") # video 或 normal
    
    # 图片列表
    image_list = data.get("imageList", [])
    result["images"] = []
    for img in image_list:
        # 提取无水印 key 或 url
        # 注意：通常需要将 url 中的 spectrum 或水印部分替换
        # 例如 XHS-Downloader 中有专门的 cleaner.py 或 converter.py 处理链接
        result["images"].append(img.get("urlDefault")) 

    # 视频链接
    if type_ == "video":
        # 提取 masterUrl (h264)
        video_info = data.get("video", {}).get("media", {}).get("stream", {}).get("h264", [])
        if video_info:
            result["video_url"] = video_info[0].get("masterUrl")
            
    return result
```

#### 2. 下载实现

参考: `XHS-Downloader/source/application/download.py`

*   **图片下载**：遍历 `result["images"]` 列表，使用 `httpx` 或 `requests` 下载。
*   **视频下载**：请求 `result["video_url"]` 下载。
*   **断点续传**：检查本地文件大小，设置 `Range` 请求头 (例如 `Range: bytes=1024-`)。

```python
async def download_file(url, path, filename):
    headers = {"User-Agent": "..."}
    # 检查已下载大小
    if os.path.exists(path):
        resume_byte = os.path.getsize(path)
        headers["Range"] = f"bytes={resume_byte}-"
    else:
        resume_byte = 0
        
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, headers=headers) as response:
            with open(path, "ab") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
```

## 3. 项目参考路径

*   **API 封装库**: `Spider_XHS/apis/xhs_pc_apis.py`
    *   包含最完整的 HTTP 接口定义。
*   **数据结构解析**: `XHS-Downloader/source/application/explore.py`
    *   如何从杂乱的 JSON 中提取关键信息（标题、点赞数、图片/视频地址）。
*   **下载器实现**: `XHS-Downloader/source/application/download.py`
    *   包含重试、并发控制、文件类型判断等工程化代码。


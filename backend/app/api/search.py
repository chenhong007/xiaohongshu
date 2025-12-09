"""
搜索相关 API
"""
from flask import Blueprint, jsonify, request, current_app

from ..models import Cookie

search_bp = Blueprint('search', __name__)


def get_active_cookie_str():
    """获取当前激活的 Cookie 字符串"""
    cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if cookie:
        return cookie.cookie_str
    return current_app.config.get('XHS_COOKIES', '')


@search_bp.route('/search/users', methods=['GET'])
def search_users():
    """
    搜索小红书用户
    
    查询参数:
    - keyword: 搜索关键词
    - limit: 返回数量限制，默认 10
    """
    keyword = request.args.get('keyword', '')
    limit = request.args.get('limit', 10, type=int)
    
    if not keyword:
        return jsonify([])
    
    cookie_str = get_active_cookie_str()
    if not cookie_str:
        return jsonify({'error': '请先登录小红书账号'}), 401
    
    try:
        from apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        success, msg, res = xhs_apis.search_user(keyword, cookie_str, page=1)
        
        if not success:
            current_app.logger.error(f"Search users failed: {msg}")
            return jsonify({'error': msg}), 500
        
        users = res.get('data', {}).get('users', [])
        
        # 调试：打印第一个用户的所有字段，帮助确认字段名
        if users and len(users) > 0:
            current_app.logger.info(f"Search user result fields: {list(users[0].keys())}")
            current_app.logger.info(f"First user data: {users[0]}")
        
        # 格式化返回数据
        result = []
        for idx, user in enumerate(users[:limit]):
            # 获取用户名，支持多种可能的字段名
            user_name = (user.get('nickname') or 
                        user.get('name') or 
                        user.get('nick_name') or 
                        user.get('user_name') or
                        user.get('red_id') or
                        user.get('user_id', ''))
            
            # 确保有唯一的 user_id：检查多种可能的字段名
            # 小红书 API 可能使用 'user_id', 'id', 'userid' 等不同字段名
            user_id = (user.get('user_id') or 
                      user.get('id') or 
                      user.get('userid') or 
                      user.get('userId'))
            
            # 如果仍然没有 user_id，记录警告
            if not user_id:
                current_app.logger.warning(f"User missing user_id, available fields: {list(user.keys())}")
                # 不使用 red_id 作为后备，因为它是小红书号不是真正的用户ID
                continue
            
            # 获取 xsec_token，用于后续 API 请求验证
            xsec_token = user.get('xsec_token', '')
            
            result.append({
                'id': user_id,
                'red_id': user.get('red_id', ''),
                'name': user_name,
                'image': user.get('image', ''),
                'desc': user.get('desc', ''),
                'fans': user.get('fans', ''),
                'is_verified': user.get('is_verified', False),
                'xsec_token': xsec_token,
            })
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Search users error: {e}")
        return jsonify({'error': str(e)}), 500


@search_bp.route('/search/notes', methods=['GET'])
def search_notes():
    """
    搜索小红书笔记
    
    查询参数:
    - keyword: 搜索关键词
    - page: 页码
    - sort: 排序方式 (0=综合, 1=最新, 2=最多点赞)
    - note_type: 笔记类型 (0=不限, 1=视频, 2=图文)
    """
    keyword = request.args.get('keyword', '')
    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 0, type=int)
    note_type = request.args.get('note_type', 0, type=int)
    
    if not keyword:
        return jsonify({'success': True, 'data': {'items': [], 'has_more': False}})
    
    cookie_str = get_active_cookie_str()
    if not cookie_str:
        return jsonify({'error': '请先登录小红书账号'}), 401
    
    try:
        from apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        success, msg, res = xhs_apis.search_note(keyword, cookie_str, page=page, 
                                                  sort_type_choice=sort, note_type=note_type)
        
        if not success:
            current_app.logger.error(f"Search notes failed: {msg}")
            return jsonify({'error': msg}), 500
        
        items = res.get('data', {}).get('items', [])
        has_more = res.get('data', {}).get('has_more', False)
        
        # 格式化返回数据
        result = []
        for item in items:
            note_card = item.get('note_card', {})
            user = note_card.get('user', {})
            result.append({
                'note_id': item.get('id'),
                'xsec_token': item.get('xsec_token'),
                'title': note_card.get('title', ''),
                'desc': note_card.get('desc', ''),
                'type': note_card.get('type'),
                'cover': note_card.get('cover', {}).get('url', ''),
                'liked_count': note_card.get('interact_info', {}).get('liked_count', 0),
                'user': {
                    'user_id': user.get('user_id'),
                    'nickname': user.get('nickname'),
                    'avatar': user.get('avatar'),
                }
            })
        
        return jsonify({
            'success': True,
            'data': {
                'items': result,
                'has_more': has_more
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Search notes error: {e}")
        return jsonify({'error': str(e)}), 500


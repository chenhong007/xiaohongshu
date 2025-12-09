"""
笔记管理 API
"""
from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from ..extensions import db
from ..models import Note, Account

notes_bp = Blueprint('notes', __name__)


@notes_bp.route('/notes', methods=['GET'])
def get_notes():
    """
    获取笔记列表
    
    查询参数:
    - user_ids: 用户ID列表，逗号分隔
    - keyword: 标题关键词搜索
    - match_mode: 匹配模式 (and/or)
    - time_range: 时间范围 (all/day/week/month)
    - start_date: 自定义开始日期 (YYYY-MM-DD)
    - end_date: 自定义结束日期 (YYYY-MM-DD)
    - note_type: 笔记类型 (all/图集/视频)
    - page: 页码
    - page_size: 每页数量
    - sort_by: 排序字段
    - sort_order: 排序方向 (asc/desc)
    """
    # 获取查询参数
    user_ids = request.args.get('user_ids', '')
    keyword = request.args.get('keyword', '')
    match_mode = request.args.get('match_mode', 'and')
    time_range = request.args.get('time_range', 'all')
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    note_type = request.args.get('note_type', 'all')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    sort_by = request.args.get('sort_by', 'upload_time')
    sort_order = request.args.get('sort_order', 'desc')
    
    # 构建查询
    query = Note.query
    
    # 用户筛选
    if user_ids:
        user_id_list = [uid.strip() for uid in user_ids.split(',') if uid.strip()]
        if user_id_list:
            query = query.filter(Note.user_id.in_(user_id_list))
    
    # 关键词搜索
    if keyword:
        keywords = keyword.split()
        if match_mode == 'or':
            # OR 模式：任意关键词匹配
            conditions = [Note.title.contains(k) | Note.desc.contains(k) for k in keywords]
            query = query.filter(or_(*conditions))
        else:
            # AND 模式：所有关键词都要匹配
            for k in keywords:
                query = query.filter(Note.title.contains(k) | Note.desc.contains(k))
    
    # 时间范围筛选
    from datetime import datetime, timedelta
    
    # 优先使用自定义日期
    if start_date_str or end_date_str:
        if start_date_str:
            try:
                # 验证日期格式
                datetime.strptime(start_date_str, '%Y-%m-%d')
                # upload_time 是字符串格式 (如 "2024-12-01" 或 "2024-12-01 10:30:00")
                query = query.filter(Note.upload_time >= start_date_str)
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # 结束日期加一天，包含当天
                end_date = end_date + timedelta(days=1)
                query = query.filter(Note.upload_time < end_date.strftime('%Y-%m-%d'))
            except ValueError:
                pass
    elif time_range != 'all':
        now = datetime.now()
        if time_range == 'day':
            start_date = now - timedelta(days=1)
        elif time_range == 'week':
            start_date = now - timedelta(weeks=1)
        elif time_range == 'month':
            start_date = now - timedelta(days=30)
        else:
            start_date = None
        
        if start_date:
            # 使用 upload_time (发布时间) 进行过滤，而不是 last_updated (同步时间)
            start_date_str = start_date.strftime('%Y-%m-%d')
            query = query.filter(Note.upload_time >= start_date_str)
    
    # 类型筛选
    if note_type != 'all':
        query = query.filter(Note.type == note_type)
    
    # 排序
    sort_column = getattr(Note, sort_by, Note.upload_time)
    if sort_order == 'desc':
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # 分页
    total = query.count()
    notes = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify({
        'success': True,
        'data': {
            'items': [note.to_dict() for note in notes],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size
        }
    })


@notes_bp.route('/notes/<note_id>', methods=['GET'])
def get_note(note_id):
    """获取单个笔记详情"""
    note = Note.query.get_or_404(note_id)
    return jsonify({'success': True, 'data': note.to_dict()})


@notes_bp.route('/notes/<note_id>', methods=['DELETE'])
def delete_note(note_id):
    """删除笔记"""
    note = Note.query.get_or_404(note_id)
    db.session.delete(note)
    db.session.commit()
    return jsonify({'success': True})


@notes_bp.route('/notes/batch-delete', methods=['POST'])
def batch_delete_notes():
    """批量删除笔记"""
    note_ids = request.json.get('note_ids', [])
    if not note_ids:
        return jsonify({'error': 'No note_ids provided'}), 400
    
    Note.query.filter(Note.note_id.in_(note_ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True, 'deleted': len(note_ids)})


@notes_bp.route('/notes/stats', methods=['GET'])
def get_notes_stats():
    """获取笔记统计信息"""
    total_notes = Note.query.count()
    total_accounts = Account.query.count()
    
    # 按类型统计
    type_stats = db.session.query(
        Note.type, db.func.count(Note.note_id)
    ).group_by(Note.type).all()
    
    return jsonify({
        'success': True,
        'data': {
            'total_notes': total_notes,
            'total_accounts': total_accounts,
            'type_stats': {t: c for t, c in type_stats}
        }
    })


@notes_bp.route('/notes/export', methods=['POST'])
def export_notes():
    """导出笔记数据"""
    note_ids = request.json.get('note_ids', [])
    export_format = request.json.get('format', 'json')  # json / excel
    
    if note_ids:
        notes = Note.query.filter(Note.note_id.in_(note_ids)).all()
    else:
        notes = Note.query.all()
    
    data = [note.to_dict() for note in notes]
    
    # TODO: 实现 Excel 导出
    return jsonify({
        'success': True,
        'data': data,
        'count': len(data)
    })


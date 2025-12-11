"""
笔记管理 API
"""
import logging
import os

from flask import Blueprint, jsonify, request, send_from_directory
from sqlalchemy import or_

from ..extensions import db
from ..models import Note, Account
from ..config import Config

notes_bp = Blueprint('notes', __name__)
logger = logging.getLogger(__name__)


@notes_bp.route('/media/<path:filename>', methods=['GET'])
def get_note_media(filename):
    """提供本地缓存的笔记封面/图片预览"""
    Config.init_paths()
    filepath = os.path.join(Config.MEDIA_PATH, filename)

    # 文件缺失时尝试按命名规则回源下载（避免重启/重新部署后封面丢失）
    if (not os.path.exists(filepath)) or os.path.getsize(filepath) == 0:
        try:
            _restore_cover_if_missing(filename)
        except Exception as e:
            logger.info(f"Restore media failed for {filename}: {e}")

    if not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'media not found'}), 404

    return send_from_directory(Config.MEDIA_PATH, filename)


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
    - liked_count_min: 点赞数最小值
    - collected_count_min: 收藏数最小值
    - comment_count_min: 评论数最小值
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
    
    # 数值过滤参数（最小值）
    liked_count_min = request.args.get('liked_count_min', type=int)
    collected_count_min = request.args.get('collected_count_min', type=int)
    comment_count_min = request.args.get('comment_count_min', type=int)
    share_count_min = request.args.get('share_count_min', type=int)
    
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
    from sqlalchemy import and_, case, func
    
    # 优先使用自定义日期
    if start_date_str or end_date_str:
        if start_date_str:
            try:
                # 验证日期格式
                start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
                # upload_time 是字符串格式 (如 "2024-12-01" 或 "2024-12-01 10:30:00")
                # 对于空的 upload_time，回退使用 last_updated (同步时间)
                query = query.filter(
                    or_(
                        # upload_time 有值且满足条件
                        and_(
                            Note.upload_time.isnot(None),
                            Note.upload_time != '',
                            Note.upload_time >= start_date_str
                        ),
                        # upload_time 为空但 last_updated 满足条件
                        and_(
                            or_(Note.upload_time.is_(None), Note.upload_time == ''),
                            Note.last_updated >= start_dt
                        )
                    )
                )
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # 结束日期加一天，包含当天
                end_date_next = end_date + timedelta(days=1)
                query = query.filter(
                    or_(
                        # upload_time 有值且满足条件
                        and_(
                            Note.upload_time.isnot(None),
                            Note.upload_time != '',
                            Note.upload_time < end_date_next.strftime('%Y-%m-%d')
                        ),
                        # upload_time 为空但 last_updated 满足条件
                        and_(
                            or_(Note.upload_time.is_(None), Note.upload_time == ''),
                            Note.last_updated < end_date_next
                        )
                    )
                )
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
            # 使用 upload_time (发布时间) 进行过滤
            # 对于空的 upload_time，回退使用 last_updated (同步时间)
            start_date_str = start_date.strftime('%Y-%m-%d')
            query = query.filter(
                or_(
                    # upload_time 有值且满足条件
                    and_(
                        Note.upload_time.isnot(None),
                        Note.upload_time != '',
                        Note.upload_time >= start_date_str
                    ),
                    # upload_time 为空但 last_updated 满足条件
                    and_(
                        or_(Note.upload_time.is_(None), Note.upload_time == ''),
                        Note.last_updated >= start_date
                    )
                )
            )
    
    # 类型筛选
    if note_type != 'all':
        query = query.filter(Note.type == note_type)
    
    # 数值过滤（最小值）
    if liked_count_min is not None:
        query = query.filter(Note.liked_count >= liked_count_min)
    if collected_count_min is not None:
        query = query.filter(Note.collected_count >= collected_count_min)
    if comment_count_min is not None:
        query = query.filter(Note.comment_count >= comment_count_min)
    if share_count_min is not None:
        query = query.filter(Note.share_count >= share_count_min)
    
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


@notes_bp.route('/media/stats', methods=['GET'])
def get_media_stats():
    """获取媒体文件统计信息"""
    Config.init_paths()
    
    # 统计数据库中的封面情况
    total_notes = Note.query.count()
    with_cover_local = Note.query.filter(
        Note.cover_local.isnot(None),
        Note.cover_local != ''
    ).count()
    with_cover_remote = Note.query.filter(
        Note.cover_remote.isnot(None),
        Note.cover_remote != ''
    ).count()
    missing_local_cover = Note.query.filter(
        Note.cover_remote.isnot(None),
        Note.cover_remote != '',
        (Note.cover_local.is_(None) | (Note.cover_local == ''))
    ).count()
    
    # 统计本地文件情况
    media_path = Config.MEDIA_PATH
    cover_files = []
    note_dirs = []
    total_size = 0
    
    if os.path.exists(media_path):
        for item in os.listdir(media_path):
            item_path = os.path.join(media_path, item)
            if os.path.isfile(item_path):
                cover_files.append({
                    'name': item,
                    'size': os.path.getsize(item_path)
                })
                total_size += os.path.getsize(item_path)
            elif os.path.isdir(item_path):
                # 笔记专属目录（包含所有媒体）
                dir_size = sum(
                    os.path.getsize(os.path.join(item_path, f))
                    for f in os.listdir(item_path)
                    if os.path.isfile(os.path.join(item_path, f))
                )
                file_count = len([f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))])
                note_dirs.append({
                    'note_id': item,
                    'file_count': file_count,
                    'size': dir_size
                })
                total_size += dir_size
    
    return jsonify({
        'success': True,
        'data': {
            'database': {
                'total_notes': total_notes,
                'with_cover_local': with_cover_local,
                'with_cover_remote': with_cover_remote,
                'missing_local_cover': missing_local_cover
            },
            'local_files': {
                'cover_files_count': len(cover_files),
                'note_dirs_count': len(note_dirs),
                'total_size_mb': round(total_size / 1024 / 1024, 2),
                'media_path': media_path
            },
            'note_dirs': note_dirs[:20] if note_dirs else [],  # 只返回前20个目录
            'sample_covers': cover_files[:20] if cover_files else []  # 只返回前20个封面
        }
    })


@notes_bp.route('/media/list', methods=['GET'])
def list_media_files():
    """列出本地媒体文件"""
    Config.init_paths()
    media_path = Config.MEDIA_PATH
    
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    filter_type = request.args.get('type', 'all')  # all, cover, dir
    
    files = []
    dirs = []
    
    if os.path.exists(media_path):
        for item in os.listdir(media_path):
            item_path = os.path.join(media_path, item)
            if os.path.isfile(item_path):
                files.append({
                    'name': item,
                    'type': 'cover',
                    'size': os.path.getsize(item_path),
                    'url': f'/api/media/{item}'
                })
            elif os.path.isdir(item_path):
                file_list = [f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))]
                dirs.append({
                    'name': item,
                    'type': 'dir',
                    'file_count': len(file_list),
                    'files': file_list[:10]  # 只返回前10个文件名
                })
    
    # 根据过滤类型返回
    if filter_type == 'cover':
        items = files
    elif filter_type == 'dir':
        items = dirs
    else:
        items = files + dirs
    
    # 分页
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    
    return jsonify({
        'success': True,
        'data': {
            'items': items[start:end],
            'total': total,
            'page': page,
            'page_size': page_size
        }
    })


@notes_bp.route('/notes/export', methods=['POST'])
def export_notes():
    """
    导出笔记数据
    
    支持两种模式：
    1. 传入 note_ids 列表，导出指定笔记
    2. 传入筛选条件，导出筛选结果
    """
    from datetime import datetime, timedelta
    from sqlalchemy import and_
    
    data = request.json or {}
    note_ids = data.get('note_ids', [])
    export_format = data.get('format', 'json')  # json / excel
    
    if note_ids:
        # 模式1：导出指定笔记
        notes = Note.query.filter(Note.note_id.in_(note_ids)).all()
    else:
        # 模式2：按筛选条件导出
        user_ids = data.get('user_ids', '')
        keyword = data.get('keyword', '')
        match_mode = data.get('match_mode', 'and')
        time_range = data.get('time_range', 'all')
        start_date_str = data.get('start_date', '')
        end_date_str = data.get('end_date', '')
        note_type = data.get('note_type', 'all')
        
        # 数值过滤参数（最小值）
        liked_count_min = data.get('liked_count_min')
        collected_count_min = data.get('collected_count_min')
        comment_count_min = data.get('comment_count_min')
        share_count_min = data.get('share_count_min')
        
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
                conditions = [Note.title.contains(k) | Note.desc.contains(k) for k in keywords]
                query = query.filter(or_(*conditions))
            else:
                for k in keywords:
                    query = query.filter(Note.title.contains(k) | Note.desc.contains(k))
        
        # 时间范围筛选
        if start_date_str or end_date_str:
            if start_date_str:
                try:
                    start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
                    query = query.filter(
                        or_(
                            and_(
                                Note.upload_time.isnot(None),
                                Note.upload_time != '',
                                Note.upload_time >= start_date_str
                            ),
                            and_(
                                or_(Note.upload_time.is_(None), Note.upload_time == ''),
                                Note.last_updated >= start_dt
                            )
                        )
                    )
                except ValueError:
                    pass
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    end_date_next = end_date + timedelta(days=1)
                    query = query.filter(
                        or_(
                            and_(
                                Note.upload_time.isnot(None),
                                Note.upload_time != '',
                                Note.upload_time < end_date_next.strftime('%Y-%m-%d')
                            ),
                            and_(
                                or_(Note.upload_time.is_(None), Note.upload_time == ''),
                                Note.last_updated < end_date_next
                            )
                        )
                    )
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
                start_date_str_calc = start_date.strftime('%Y-%m-%d')
                query = query.filter(
                    or_(
                        and_(
                            Note.upload_time.isnot(None),
                            Note.upload_time != '',
                            Note.upload_time >= start_date_str_calc
                        ),
                        and_(
                            or_(Note.upload_time.is_(None), Note.upload_time == ''),
                            Note.last_updated >= start_date
                        )
                    )
                )
        
        # 类型筛选
        if note_type != 'all':
            query = query.filter(Note.type == note_type)
        
        # 数值过滤（最小值）
        if liked_count_min is not None:
            query = query.filter(Note.liked_count >= liked_count_min)
        if collected_count_min is not None:
            query = query.filter(Note.collected_count >= collected_count_min)
        if comment_count_min is not None:
            query = query.filter(Note.comment_count >= comment_count_min)
        if share_count_min is not None:
            query = query.filter(Note.share_count >= share_count_min)
        
        notes = query.all()
    
    result_data = [note.to_dict() for note in notes]
    
    # TODO: 实现 Excel 导出
    return jsonify({
        'success': True,
        'data': result_data,
        'count': len(result_data)
    })


def _restore_cover_if_missing(filename: str) -> bool:
    """当封面文件缺失时尝试从远程重新下载并刷新数据库路径"""
    if not filename or '_cover' not in filename:
        return False
    try:
        note = Note.query.filter(Note.cover_local.like(f"%/{filename}")).first()
        if not note or not note.cover_remote:
            return False
        # 延迟导入以避免潜在循环依赖
        from ..services.sync_service import SyncService
        cover_local = SyncService._download_cover(note.cover_remote, note.note_id)
        if cover_local:
            note.cover_local = cover_local
            db.session.commit()
            return True
    except Exception as e:
        db.session.rollback()
        logger.info(f"Restore cover error for {filename}: {e}")
    return False


"""
账号管理 API
"""
from flask import Blueprint, request
from datetime import datetime

from ..extensions import db
from ..models import Account
from ..services.sync_service import SyncService
from ..utils.responses import ApiResponse, success_response, error_response
from ..utils.validators import validate_user_id, validate_ids_list, validate_sync_mode, sanitize_string
from ..utils.logger import get_logger
from ..middleware.auth import require_admin

accounts_bp = Blueprint('accounts', __name__)
logger = get_logger('accounts')


@accounts_bp.route('/accounts', methods=['GET'])
def get_accounts():
    """
    获取所有账号列表
    
    Returns:
        账号列表数组
    """
    try:
        accounts = Account.query.order_by(Account.id.desc()).all()
        return success_response(
            data=[acc.to_dict() for acc in accounts],
            message=f'获取成功，共 {len(accounts)} 个账号'
        )
    except Exception as e:
        logger.error(f"获取账号列表失败: {e}")
        return ApiResponse.server_error('获取账号列表失败')


@accounts_bp.route('/accounts/status', methods=['GET'])
def get_accounts_status():
    """
    获取账号同步状态（轻量级）
    
    只返回同步状态相关字段，用于前端轮询，避免序列化 sync_logs 等大字段
    
    Returns:
        状态列表数组: [{id, status, progress, loaded_msgs, total_msgs, error_message, last_sync}]
    """
    try:
        accounts = Account.query.with_entities(
            Account.id,
            Account.status,
            Account.progress,
            Account.loaded_msgs,
            Account.total_msgs,
            Account.error_message,
            Account.last_sync
        ).order_by(Account.id.desc()).all()
        
        result = [{
            'id': acc.id,
            'status': acc.status,
            'progress': acc.progress,
            'loaded_msgs': acc.loaded_msgs,
            'total_msgs': acc.total_msgs,
            'error_message': acc.error_message,
            'last_sync': acc.last_sync.isoformat() + 'Z' if acc.last_sync else None,
        } for acc in accounts]
        
        return success_response(data=result)
    except Exception as e:
        logger.error(f"获取账号状态失败: {e}")
        return ApiResponse.server_error('获取账号状态失败')


@accounts_bp.route('/accounts', methods=['POST'])
def add_account():
    """
    添加账号
    
    Request Body:
        - user_id: 用户ID (必填)
        - name: 用户名
        - avatar: 头像URL
        - red_id: 小红书号
        - desc: 简介
        - fans: 粉丝数
    """
    data = request.json or {}
    
    # 验证 user_id
    user_id = data.get('user_id', '').strip() if data.get('user_id') else ''
    is_valid, error_msg = validate_user_id(user_id)
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    # 检查是否已存在
    existing = Account.query.filter_by(user_id=user_id).first()
    if existing:
        return ApiResponse.error('该账号已添加过', 409, 'DUPLICATE_ACCOUNT')
    
    # 创建新账号
    try:
        account = Account(
            user_id=user_id,
            name=sanitize_string(data.get('name'), 128) or user_id,
            avatar=sanitize_string(data.get('avatar'), 512),
            red_id=sanitize_string(data.get('red_id'), 64),
            desc=sanitize_string(data.get('desc'), 1000),
            fans=int(data.get('fans', 0)) if data.get('fans') else 0,
        )
        
        db.session.add(account)
        db.session.commit()
        
        logger.info(f"添加账号成功: {user_id}")
        return ApiResponse.created(account.to_dict(), '账号添加成功')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"添加账号失败: {e}")
        return ApiResponse.server_error('添加账号失败')


@accounts_bp.route('/accounts/<int:account_id>', methods=['GET'])
def get_account(account_id):
    """获取单个账号详情"""
    account = Account.query.get(account_id)
    if not account:
        return ApiResponse.not_found('账号不存在')
    return success_response(account.to_dict())


@accounts_bp.route('/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """删除单个账号"""
    account = Account.query.get(account_id)
    if not account:
        return ApiResponse.not_found('账号不存在')
    
    try:
        user_id = account.user_id
        db.session.delete(account)
        db.session.commit()
        logger.info(f"删除账号: {user_id}")
        return success_response(message='删除成功')
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除账号失败: {e}")
        return ApiResponse.server_error('删除失败')


@accounts_bp.route('/accounts/batch-delete', methods=['POST'])
def batch_delete_accounts():
    """
    批量删除账号
    
    Request Body:
        - ids: 账号ID数组 (最多100个)
    """
    data = request.json or {}
    
    # 验证 ID 列表
    is_valid, error_msg, ids = validate_ids_list(
        data.get('ids'),
        max_count=100,
        field_name='账号ID'
    )
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    try:
        deleted_count = Account.query.filter(Account.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        logger.info(f"批量删除账号: {deleted_count} 个")
        return success_response(
            data={'deleted': deleted_count},
            message=f'成功删除 {deleted_count} 个账号'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"批量删除失败: {e}")
        return ApiResponse.server_error('批量删除失败')


@accounts_bp.route('/accounts/<int:account_id>/sync', methods=['POST'])
def sync_account(account_id):
    """
    同步单个账号的笔记
    
    Request Body:
        - mode: 同步模式 ('fast' | 'deep')
    """
    # Check Cookie validity before starting sync
    cookie_valid, cookie_error = SyncService.check_cookie_valid()
    if not cookie_valid:
        return ApiResponse.error(cookie_error, 401, 'INVALID_COOKIE')
    
    account = Account.query.get(account_id)
    if not account:
        return ApiResponse.not_found('账号不存在')
    
    data = request.json or {}
    is_valid, error_msg, mode = validate_sync_mode(data.get('mode'))
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    # 尝试启动同步（会检查是否已有同步任务在运行）
    success, message = SyncService.start_sync([account_id], sync_mode=mode)
    if not success:
        return ApiResponse.error(message, 409, 'SYNC_IN_PROGRESS')
    
    logger.info(f"开始同步账号 {account.user_id}，模式: {mode}")
    
    return success_response(message=f'开始同步，模式: {mode}')


@accounts_bp.route('/accounts/sync-batch', methods=['POST'])
def sync_batch():
    """
    批量同步账号
    
    Request Body:
        - ids: 账号ID数组
        - mode: 同步模式 ('fast' | 'deep')
    """
    # Check Cookie validity before starting sync
    cookie_valid, cookie_error = SyncService.check_cookie_valid()
    if not cookie_valid:
        return ApiResponse.error(cookie_error, 401, 'INVALID_COOKIE')
    
    data = request.json or {}
    
    # 验证 ID 列表
    is_valid, error_msg, ids = validate_ids_list(
        data.get('ids'),
        max_count=50,
        field_name='账号ID'
    )
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    # 验证同步模式
    is_valid, error_msg, mode = validate_sync_mode(data.get('mode'))
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    # 先检查是否有同步任务在运行，避免无谓的状态更新
    if SyncService.is_sync_running():
        return ApiResponse.error('已有同步任务正在运行，请等待当前任务完成或停止后再试', 409, 'SYNC_IN_PROGRESS')
    
    # 重置状态
    Account.query.filter(Account.id.in_(ids)).update(
        {'status': 'pending', 'progress': 0, 'error_message': None},
        synchronize_session=False
    )
    db.session.commit()
    
    # 尝试启动同步
    success, message = SyncService.start_sync(ids, sync_mode=mode)
    if not success:
        # 回滚状态（理论上不应该发生，因为上面已经检查过）
        Account.query.filter(Account.id.in_(ids)).update(
            {'status': 'failed', 'error_message': message},
            synchronize_session=False
        )
        db.session.commit()
        return ApiResponse.error(message, 409, 'SYNC_IN_PROGRESS')
    
    logger.info(f"开始批量同步 {len(ids)} 个账号，模式: {mode}，IDs: {ids}")
    
    return success_response(
        data={'count': len(ids)},
        message=f'开始同步 {len(ids)} 个账号'
    )


@accounts_bp.route('/accounts/sync-all', methods=['POST'])
def sync_all():
    """
    同步所有账号
    
    Request Body:
        - mode: 同步模式 ('fast' | 'deep')
    """
    # Check Cookie validity before starting sync
    cookie_valid, cookie_error = SyncService.check_cookie_valid()
    if not cookie_valid:
        return ApiResponse.error(cookie_error, 401, 'INVALID_COOKIE')
    
    data = request.json or {}
    
    is_valid, error_msg, mode = validate_sync_mode(data.get('mode'))
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    accounts = Account.query.all()
    ids = [acc.id for acc in accounts]
    
    if not ids:
        return ApiResponse.error('没有可同步的账号', 400, 'NO_ACCOUNTS')
    
    # 先检查是否有同步任务在运行，避免无谓的状态更新
    if SyncService.is_sync_running():
        return ApiResponse.error('已有同步任务正在运行，请等待当前任务完成或停止后再试', 409, 'SYNC_IN_PROGRESS')
    
    Account.query.update({
        'status': 'pending',
        'progress': 0,
        'error_message': None
    })
    db.session.commit()
    
    # 尝试启动同步
    success, message = SyncService.start_sync(ids, sync_mode=mode)
    if not success:
        # 回滚状态
        Account.query.update({
            'status': 'failed',
            'error_message': message
        })
        db.session.commit()
        return ApiResponse.error(message, 409, 'SYNC_IN_PROGRESS')
    
    logger.info(f"开始同步所有账号 ({len(ids)} 个)，模式: {mode}")
    
    return success_response(
        data={'count': len(ids)},
        message=f'开始同步全部 {len(ids)} 个账号'
    )


@accounts_bp.route('/accounts/stop-sync', methods=['POST'])
def stop_sync():
    """停止同步任务 - 优化：立即返回响应，后台处理数据库更新"""
    import threading
    from flask import current_app
    
    # 获取当前同步模式
    mode_name = '深度同步' if SyncService._current_sync_mode == 'deep' else '极速同步'
    
    # 立即设置停止标志（这是内存操作，非常快）
    SyncService.stop_sync()
    
    # 在后台线程中更新数据库状态，避免阻塞响应
    def update_accounts_status(app, mode_name):
        with app.app_context():
            try:
                updated = Account.query.filter(Account.status.in_(['processing', 'pending'])).update(
                    {
                        'status': 'failed',
                        'progress': 0,
                        'error_message': f'用户手动停止{mode_name}'
                    },
                    synchronize_session=False
                )
                db.session.commit()
                logger.info(f"停止同步，影响 {updated} 个账号")
            except Exception as e:
                logger.error(f"更新账号状态失败: {e}")
                db.session.rollback()
    
    # 启动后台线程处理数据库更新
    app = current_app._get_current_object()
    thread = threading.Thread(target=update_accounts_status, args=(app, mode_name))
    thread.daemon = True
    thread.start()
    
    # 立即返回响应
    return success_response(message='正在停止同步任务')


@accounts_bp.route('/accounts/<int:account_id>/sync-logs', methods=['GET'])
def get_account_sync_logs(account_id):
    """
    分页获取账号的同步日志 issues
    
    Query Parameters:
        - page: 页码，默认 1
        - page_size: 每页数量，默认 50，最大 200
        - type: 可选，筛选特定类型的问题 (rate_limited, unavailable, missing_field, fetch_failed, token_refresh, media_failed, auth_error)
    
    Returns:
        {
            issues: [{type, note_id, message, time, ...}],
            total: int,
            page: int,
            page_size: int,
            total_pages: int,
            summary: {...}  # 同步摘要信息
        }
    """
    account = Account.query.get(account_id)
    if not account:
        return ApiResponse.not_found('账号不存在')
    
    try:
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 50)), 200)  # max 200
        issue_type = request.args.get('type')
        
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 50
        
        # Get paginated issues
        result = account.get_sync_logs_issues(page=page, page_size=page_size, issue_type=issue_type)
        
        # Add summary info
        if account.sync_logs:
            import json
            try:
                full_logs = json.loads(account.sync_logs)
                result['summary'] = full_logs.get('summary')
                result['sync_mode'] = full_logs.get('sync_mode')
                result['start_time'] = full_logs.get('start_time')
                result['end_time'] = full_logs.get('end_time')
            except (json.JSONDecodeError, TypeError):
                result['summary'] = None
        
        return success_response(data=result)
    except Exception as e:
        logger.error(f"获取同步日志失败: {e}")
        return ApiResponse.server_error('获取同步日志失败')


@accounts_bp.route('/accounts/<int:account_id>/fix-missing', methods=['POST'])
def fix_missing_fields(account_id):
    """
    补齐指定博主的缺失字段（发布时间、收藏数、评论数等）
    
    这个功能用于修复之前用极速同步采集的笔记，补齐详情页数据。
    
    Request Body:
        - force: 是否强制重新采集所有笔记 (默认 false，只采集缺失字段的笔记)
    """
    # Check Cookie validity before starting sync
    cookie_valid, cookie_error = SyncService.check_cookie_valid()
    if not cookie_valid:
        return ApiResponse.error(cookie_error, 401, 'INVALID_COOKIE')
    
    from ..models import Note
    
    account = Account.query.get(account_id)
    if not account:
        return ApiResponse.not_found('账号不存在')
    
    data = request.json or {}
    force = data.get('force', False)
    
    try:
        # 统计该博主缺失 upload_time 的笔记数量
        query = Note.query.filter_by(user_id=account.user_id)
        
        if not force:
            # 只查询缺失 upload_time 的笔记
            from sqlalchemy import or_
            query = query.filter(or_(
                Note.upload_time.is_(None),
                Note.upload_time == ''
            ))
        
        missing_count = query.count()
        
        if missing_count == 0:
            return success_response(
                data={'missing_count': 0},
                message='该博主的所有笔记都已有完整的发布时间'
            )
        
        # 启动深度同步（会自动检测并补齐缺失字段）
        success, message = SyncService.start_sync([account_id], sync_mode='deep')
        if not success:
            return ApiResponse.error(message, 409, 'SYNC_IN_PROGRESS')
        
        logger.info(f"开始补齐账号 {account.user_id} 的缺失字段，共 {missing_count} 条笔记需要处理")
        
        return success_response(
            data={'missing_count': missing_count},
            message=f'开始补齐缺失数据，共 {missing_count} 条笔记需要处理'
        )
    except Exception as e:
        logger.error(f"补齐缺失字段失败: {e}")
        return ApiResponse.server_error('补齐缺失字段失败')


@accounts_bp.route('/accounts/stats/missing', methods=['GET'])
def get_missing_stats():
    """
    获取所有博主的缺失字段统计
    
    返回每个博主缺失 upload_time 的笔记数量
    """
    from ..models import Note
    from sqlalchemy import func, or_
    
    try:
        # 查询每个博主缺失 upload_time 的笔记数量
        missing_stats = db.session.query(
            Account.id,
            Account.user_id,
            Account.name,
            func.count(Note.id).label('missing_count')
        ).outerjoin(
            Note,
            (Account.user_id == Note.user_id) & 
            (or_(Note.upload_time.is_(None), Note.upload_time == ''))
        ).group_by(Account.id).all()
        
        result = []
        for stat in missing_stats:
            result.append({
                'account_id': stat.id,
                'user_id': stat.user_id,
                'name': stat.name,
                'missing_upload_time_count': stat.missing_count or 0
            })
        
        total_missing = sum(s['missing_upload_time_count'] for s in result)
        
        return success_response(
            data={
                'accounts': result,
                'total_missing': total_missing
            },
            message=f'共有 {total_missing} 条笔记缺失发布时间'
        )
    except Exception as e:
        logger.error(f"获取缺失统计失败: {e}")
        return ApiResponse.server_error('获取缺失统计失败')


@accounts_bp.route('/reset', methods=['POST'])
@require_admin  # 🔒 需要管理员权限
def reset_db():
    """
    清空所有数据（危险操作）
    
    ⚠️ 需要管理员 API Key
    """
    from ..models import Note
    
    try:
        note_count = Note.query.count()
        account_count = Account.query.count()
        
        Note.query.delete()
        Account.query.delete()
        db.session.commit()
        
        logger.warning(f"数据库已清空: {account_count} 个账号, {note_count} 条笔记")
        
        return success_response(
            data={
                'deleted_accounts': account_count,
                'deleted_notes': note_count
            },
            message='数据库已清空'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"清空数据库失败: {e}")
        return ApiResponse.server_error('清空数据库失败')


@accounts_bp.route('/accounts/export', methods=['POST'])
def export_accounts():
    """
    导出账号数据（包含关联的笔记数据）
    
    Request Body:
        - ids: 账号ID数组（可选，为空则导出全部）
        - include_notes: 是否包含笔记数据（默认 true）
    
    Returns:
        {
            accounts: [...],
            notes: [...],
            export_time: "2025-12-16T10:00:00",
            version: "1.0"
        }
    """
    from ..models import Note
    from datetime import datetime
    
    data = request.json or {}
    ids = data.get('ids', [])
    include_notes = data.get('include_notes', True)
    
    try:
        # 获取账号数据
        if ids:
            accounts = Account.query.filter(Account.id.in_(ids)).all()
        else:
            accounts = Account.query.all()
        
        accounts_data = [acc.to_dict() for acc in accounts]
        
        # 获取关联的笔记数据
        notes_data = []
        if include_notes and accounts:
            user_ids = [acc.user_id for acc in accounts]
            notes = Note.query.filter(Note.user_id.in_(user_ids)).all()
            notes_data = [note.to_dict() for note in notes]
        
        result = {
            'accounts': accounts_data,
            'notes': notes_data,
            'export_time': datetime.utcnow().isoformat() + 'Z',
            'version': '1.0'
        }
        
        logger.info(f"导出数据: {len(accounts_data)} 个账号, {len(notes_data)} 条笔记")
        
        return success_response(
            data=result,
            message=f'导出成功: {len(accounts_data)} 个账号, {len(notes_data)} 条笔记'
        )
    except Exception as e:
        logger.error(f"导出数据失败: {e}")
        return ApiResponse.server_error('导出数据失败')


@accounts_bp.route('/accounts/import', methods=['POST'])
def import_accounts():
    """
    导入账号数据（包含关联的笔记数据）
    
    Request Body:
        {
            accounts: [...],
            notes: [...],  # 可选
            version: "1.0"
        }
    
    导入规则：
        - 账号：如果 user_id 已存在则更新，否则新增
        - 笔记：如果 note_id 已存在则用导入数据覆盖，否则新增
    
    Returns:
        {
            accounts_added: int,
            accounts_updated: int,
            notes_added: int,
            notes_updated: int
        }
    """
    from ..models import Note
    import json
    
    data = request.json or {}
    accounts_data = data.get('accounts', [])
    notes_data = data.get('notes', [])
    
    if not accounts_data and not notes_data:
        return ApiResponse.validation_error('导入数据为空')
    
    accounts_added = 0
    accounts_updated = 0
    notes_added = 0
    notes_updated = 0
    
    try:
        # 导入账号
        for acc_data in accounts_data:
            user_id = acc_data.get('user_id')
            if not user_id:
                continue
            
            existing = Account.query.filter_by(user_id=user_id).first()
            if existing:
                # 更新现有账号（不覆盖同步状态相关字段）
                existing.name = acc_data.get('name') or existing.name
                existing.avatar = acc_data.get('avatar') or existing.avatar
                existing.red_id = acc_data.get('red_id') or existing.red_id
                existing.desc = acc_data.get('desc') or existing.desc
                existing.fans = acc_data.get('fans', existing.fans)
                accounts_updated += 1
            else:
                # 新增账号
                account = Account(
                    user_id=user_id,
                    name=acc_data.get('name') or user_id,
                    avatar=acc_data.get('avatar'),
                    red_id=acc_data.get('red_id'),
                    desc=acc_data.get('desc'),
                    fans=acc_data.get('fans', 0),
                )
                db.session.add(account)
                accounts_added += 1
        
        db.session.flush()  # 确保账号先写入
        
        # 导入笔记
        for note_data in notes_data:
            note_id = note_data.get('note_id')
            if not note_id:
                continue
            
            existing = Note.query.get(note_id)
            if existing:
                # 更新现有笔记（用导入数据覆盖）
                existing.user_id = note_data.get('user_id') or existing.user_id
                existing.nickname = note_data.get('nickname') or existing.nickname
                existing.avatar = note_data.get('avatar') or existing.avatar
                existing.title = note_data.get('title') or existing.title
                existing.desc = note_data.get('desc') or existing.desc
                existing.type = note_data.get('type') or existing.type
                existing.liked_count = note_data.get('liked_count', existing.liked_count)
                existing.collected_count = note_data.get('collected_count', existing.collected_count)
                existing.comment_count = note_data.get('comment_count', existing.comment_count)
                existing.share_count = note_data.get('share_count', existing.share_count)
                existing.upload_time = note_data.get('upload_time') or existing.upload_time
                existing.video_addr = note_data.get('video_addr') or existing.video_addr
                existing.ip_location = note_data.get('ip_location') or existing.ip_location
                existing.cover_remote = note_data.get('cover_remote') or existing.cover_remote
                existing.cover_local = note_data.get('cover_local') or existing.cover_local
                existing.xsec_token = note_data.get('xsec_token') or existing.xsec_token
                # 处理列表字段
                if note_data.get('image_list'):
                    existing.image_list = json.dumps(note_data['image_list']) if isinstance(note_data['image_list'], list) else note_data['image_list']
                if note_data.get('tags'):
                    existing.tags = json.dumps(note_data['tags']) if isinstance(note_data['tags'], list) else note_data['tags']
                notes_updated += 1
            else:
                # 新增笔记
                note = Note(
                    note_id=note_id,
                    user_id=note_data.get('user_id'),
                    nickname=note_data.get('nickname'),
                    avatar=note_data.get('avatar'),
                    title=note_data.get('title'),
                    desc=note_data.get('desc'),
                    type=note_data.get('type'),
                    liked_count=note_data.get('liked_count', 0),
                    collected_count=note_data.get('collected_count', 0),
                    comment_count=note_data.get('comment_count', 0),
                    share_count=note_data.get('share_count', 0),
                    upload_time=note_data.get('upload_time'),
                    video_addr=note_data.get('video_addr'),
                    ip_location=note_data.get('ip_location'),
                    cover_remote=note_data.get('cover_remote'),
                    cover_local=note_data.get('cover_local'),
                    xsec_token=note_data.get('xsec_token'),
                )
                # 处理列表字段
                if note_data.get('image_list'):
                    note.image_list = json.dumps(note_data['image_list']) if isinstance(note_data['image_list'], list) else note_data['image_list']
                if note_data.get('tags'):
                    note.tags = json.dumps(note_data['tags']) if isinstance(note_data['tags'], list) else note_data['tags']
                db.session.add(note)
                notes_added += 1
        
        db.session.commit()
        
        logger.info(f"导入完成: 账号新增 {accounts_added}, 更新 {accounts_updated}; 笔记新增 {notes_added}, 更新 {notes_updated}")
        
        return success_response(
            data={
                'accounts_added': accounts_added,
                'accounts_updated': accounts_updated,
                'notes_added': notes_added,
                'notes_updated': notes_updated
            },
            message=f'导入成功: 账号新增 {accounts_added} 更新 {accounts_updated}, 笔记新增 {notes_added} 更新 {notes_updated}'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"导入数据失败: {e}")
        return ApiResponse.server_error(f'导入数据失败: {str(e)}')

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
    account = Account.query.get(account_id)
    if not account:
        return ApiResponse.not_found('账号不存在')
    
    data = request.json or {}
    is_valid, error_msg, mode = validate_sync_mode(data.get('mode'))
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    SyncService.start_sync([account_id], sync_mode=mode)
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
    
    # 重置状态
    Account.query.filter(Account.id.in_(ids)).update(
        {'status': 'pending', 'progress': 0, 'error_message': None},
        synchronize_session=False
    )
    db.session.commit()
    
    SyncService.start_sync(ids, sync_mode=mode)
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
    data = request.json or {}
    
    is_valid, error_msg, mode = validate_sync_mode(data.get('mode'))
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    accounts = Account.query.all()
    ids = [acc.id for acc in accounts]
    
    if not ids:
        return ApiResponse.error('没有可同步的账号', 400, 'NO_ACCOUNTS')
    
    Account.query.update({
        'status': 'pending',
        'progress': 0,
        'error_message': None
    })
    db.session.commit()
    
    SyncService.start_sync(ids, sync_mode=mode)
    logger.info(f"开始同步所有账号 ({len(ids)} 个)，模式: {mode}")
    
    return success_response(
        data={'count': len(ids)},
        message=f'开始同步全部 {len(ids)} 个账号'
    )


@accounts_bp.route('/accounts/stop-sync', methods=['POST'])
def stop_sync():
    """停止同步任务"""
    # 获取当前同步模式
    mode_name = '深度同步' if SyncService._current_sync_mode == 'deep' else '极速同步'
    
    SyncService.stop_sync()
    
    # 将正在执行或等待执行的任务全部标记为停止，避免前端一直显示“准备中”
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
    return success_response(message='正在停止同步任务')


@accounts_bp.route('/accounts/<int:account_id>/fix-missing', methods=['POST'])
def fix_missing_fields(account_id):
    """
    补齐指定博主的缺失字段（发布时间、收藏数、评论数等）
    
    这个功能用于修复之前用极速同步采集的笔记，补齐详情页数据。
    
    Request Body:
        - force: 是否强制重新采集所有笔记 (默认 false，只采集缺失字段的笔记)
    """
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
        SyncService.start_sync([account_id], sync_mode='deep')
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

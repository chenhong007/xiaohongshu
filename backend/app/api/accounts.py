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
        - xsec_token: xsec_token
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
        # 如果已存在，更新 xsec_token（token 可能会更新）
        xsec_token = data.get('xsec_token')
        if xsec_token:
            existing.xsec_token = xsec_token
            db.session.commit()
            logger.info(f"账号 {user_id} 已存在，更新了 xsec_token")
        return ApiResponse.error('该账号已添加过', 409, 'DUPLICATE_ACCOUNT')
    
    # 创建新账号
    try:
        account = Account(
            user_id=user_id,
            name=sanitize_string(data.get('name'), 128) or user_id,
            avatar=sanitize_string(data.get('avatar'), 512),
            red_id=sanitize_string(data.get('red_id'), 64),
            xsec_token=sanitize_string(data.get('xsec_token'), 256),
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
    logger.info(f"开始批量同步 {len(ids)} 个账号，模式: {mode}")
    
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
    SyncService.stop_sync()
    
    # 将正在执行或等待执行的任务全部标记为停止，避免前端一直显示“准备中”
    updated = Account.query.filter(Account.status.in_(['processing', 'pending'])).update(
        {
            'status': 'failed',
            'progress': 0,
            'error_message': '用户手动停止同步'
        },
        synchronize_session=False
    )
    db.session.commit()
    
    logger.info(f"停止同步，影响 {updated} 个账号")
    return success_response(message='正在停止同步任务')


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

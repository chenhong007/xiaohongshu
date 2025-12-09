"""
账号管理 API
"""
from flask import Blueprint, jsonify, request
from datetime import datetime

from ..extensions import db
from ..models import Account
from ..services.sync_service import SyncService

accounts_bp = Blueprint('accounts', __name__)


@accounts_bp.route('/accounts', methods=['GET'])
def get_accounts():
    """获取所有账号列表"""
    accounts = Account.query.order_by(Account.id.desc()).all()
    return jsonify([acc.to_dict() for acc in accounts])


@accounts_bp.route('/accounts', methods=['POST'])
def add_account():
    """添加账号"""
    data = request.json
    user_id = data.get('user_id')
    name = data.get('name')
    avatar = data.get('avatar')
    xsec_token = data.get('xsec_token')
    
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400
    
    # 检查是否已存在
    existing = Account.query.filter_by(user_id=user_id).first()
    if existing:
        # 如果已存在，更新 xsec_token（token 可能会更新）
        if xsec_token:
            existing.xsec_token = xsec_token
            db.session.commit()
        return jsonify({'error': 'User already exists'}), 409
    
    account = Account(
        user_id=user_id,
        name=name,
        avatar=avatar,
        red_id=data.get('red_id'),
        xsec_token=xsec_token,
        desc=data.get('desc'),
        fans=data.get('fans', 0),
    )
    
    db.session.add(account)
    db.session.commit()
    
    return jsonify({'success': True, 'data': account.to_dict()})


@accounts_bp.route('/accounts/<int:account_id>', methods=['GET'])
def get_account(account_id):
    """获取单个账号详情"""
    account = Account.query.get_or_404(account_id)
    return jsonify(account.to_dict())


@accounts_bp.route('/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """删除账号"""
    account = Account.query.get_or_404(account_id)
    db.session.delete(account)
    db.session.commit()
    return jsonify({'success': True})


@accounts_bp.route('/accounts/batch-delete', methods=['POST'])
def batch_delete_accounts():
    """批量删除账号"""
    ids = request.json.get('ids', [])
    if not ids:
        return jsonify({'error': 'No ids provided'}), 400
    
    Account.query.filter(Account.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True, 'deleted': len(ids)})


@accounts_bp.route('/accounts/<int:account_id>/sync', methods=['POST'])
def sync_account(account_id):
    """同步单个账号的笔记"""
    SyncService.start_sync([account_id])
    return jsonify({'success': True, 'message': 'Sync started'})


@accounts_bp.route('/accounts/sync-batch', methods=['POST'])
def sync_batch():
    """批量同步账号"""
    ids = request.json.get('ids', [])
    if not ids:
        return jsonify({'error': 'No ids provided'}), 400
    
    # 重置状态
    Account.query.filter(Account.id.in_(ids)).update(
        {'status': 'pending', 'progress': 0},
        synchronize_session=False
    )
    db.session.commit()
    
    SyncService.start_sync(ids)
    return jsonify({'success': True, 'message': 'Batch sync started'})


@accounts_bp.route('/accounts/sync-all', methods=['POST'])
def sync_all():
    """同步所有账号"""
    accounts = Account.query.all()
    ids = [acc.id for acc in accounts]
    
    if ids:
        Account.query.update({'status': 'pending', 'progress': 0})
        db.session.commit()
        SyncService.start_sync(ids)
    
    return jsonify({'success': True, 'message': 'Sync all started'})


@accounts_bp.route('/reset', methods=['POST'])
def reset_db():
    """清空所有数据"""
    from ..models import Note
    Note.query.delete()
    Account.query.delete()
    db.session.commit()
    return jsonify({'success': True})


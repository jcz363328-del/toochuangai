from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from department_permissions import require_permission

# 创建蓝图
innovation_proposals_bp = Blueprint('innovation_proposals', __name__)

@innovation_proposals_bp.route('/innovation_proposals')
@require_permission('innovation_proposals')
def innovation_proposals():
    """创新提案管理入口页面"""
    # 直接重定向到统一端口下的创新系统
    return redirect(url_for('innovation.innovation_index'))

@innovation_proposals_bp.route('/check_innovation_status')
def check_innovation_status():
    """检查innovation系统状态的API（现在总是返回ready）"""
    innovation_url = "http://127.0.0.1:8080/innovation"
    return jsonify({'status': 'ready', 'url': innovation_url})
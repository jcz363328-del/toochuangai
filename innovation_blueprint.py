from flask import Blueprint
import sys
import os

# 添加innovation目录到Python路径
innovation_path = os.path.join(os.path.dirname(__file__), 'innovation')
if innovation_path not in sys.path:
    sys.path.insert(0, innovation_path)

# 导入创新系统的所有函数
from innovation.web_app import (
    index, mobile_index, submit, dashboard, points, excellent_cases, manage, manage_mobile,
    submit_innovation, get_innovations, transfer_innovation,
    request_help, get_flow_details, get_project_departments,
    handle_innovation, update_committee_score, submit_to_meeting, update_user_points_summary,
    batch_update_all_users_points, get_user_points,
    get_rewards, exchange_reward, get_point_records,
    export_innovations, get_statistics, add_reward,
    upload_reward_image, update_reward, delete_reward,
    add_reward_with_image, uploaded_file, reward_image,
    test_simple, get_dashboard_data, get_innovation_compare, export_statistics, toggle_favorite,
    add_favorite_category, innovation_react, innovation_update_comment, innovation_get_react_stats, like_image_file
)

# 创建创新系统蓝图，指定模板和静态文件路径
innovation_bp = Blueprint('innovation', __name__, 
                         url_prefix='/innovation',
                         template_folder='innovation/templates',
                         static_folder='innovation/static')

# 将创新系统的所有路由添加到蓝图中
@innovation_bp.route('/')
def innovation_index():
    """创新系统首页"""
    return index()

@innovation_bp.route('/mobile')
def innovation_mobile_index():
    """创新系统移动端首页"""
    return mobile_index()

@innovation_bp.route('/submit')
def innovation_submit():
    """提交页面"""
    return submit()

@innovation_bp.route('/dashboard')
def innovation_dashboard():
    """仪表板页面"""
    return dashboard()

@innovation_bp.route('/points')
def innovation_points():
    """积分页面"""
    return points()

@innovation_bp.route('/excellent_cases')
def innovation_excellent_cases():
    """优秀案例页面"""
    return excellent_cases()

@innovation_bp.route('/manage')
def innovation_manage():
    """管理页面"""
    return manage()

@innovation_bp.route('/manage/mobile')
def innovation_manage_mobile():
    """管理页面 - 移动版"""
    return manage_mobile()

@innovation_bp.route('/manage1')
def innovation_manage1():
    """管理页面 - 简化版"""
    from flask import render_template
    return render_template('manage1.html')

# API路由
@innovation_bp.route('/api/submit_innovation', methods=['POST'])
def innovation_submit_innovation():
    """提交创新项目API"""
    return submit_innovation()

@innovation_bp.route('/api/get_innovations', methods=['GET'])
def innovation_get_innovations():
    """获取创新项目列表API"""
    return get_innovations()

@innovation_bp.route('/api/transfer_innovation', methods=['POST'])
def innovation_transfer_innovation():
    """转移创新项目API"""
    return transfer_innovation()

@innovation_bp.route('/api/request_help', methods=['POST'])
def innovation_request_help():
    """请求帮助API"""
    return request_help()

@innovation_bp.route('/api/get_flow_details/<int:project_id>', methods=['GET'])
def innovation_get_flow_details(project_id):
    """获取流程详情API"""
    return get_flow_details(project_id)

@innovation_bp.route('/api/get_project_departments/<int:project_id>', methods=['GET'])
def innovation_get_project_departments(project_id):
    """获取项目部门API"""
    return get_project_departments(project_id)

@innovation_bp.route('/api/handle_innovation', methods=['POST'])
def innovation_handle_innovation():
    """处理创新项目API"""
    return handle_innovation()

@innovation_bp.route('/api/update_committee_score', methods=['POST'])
def innovation_update_committee_score():
    """更新委员会打分API"""
    return update_committee_score()

@innovation_bp.route('/api/submit_to_meeting', methods=['POST'])
def innovation_submit_to_meeting():
    """一键上会API"""
    return submit_to_meeting()

@innovation_bp.route('/api/update_user_points_summary', methods=['POST'])
def innovation_update_user_points_summary():
    """更新用户积分汇总API"""
    return update_user_points_summary()

@innovation_bp.route('/api/batch_update_all_users_points', methods=['POST'])
def innovation_batch_update_all_users_points():
    """批量更新所有用户积分API"""
    return batch_update_all_users_points()

@innovation_bp.route('/api/get_user_points', methods=['GET'])
def innovation_get_user_points():
    """获取用户积分API"""
    return get_user_points()

@innovation_bp.route('/api/get_rewards', methods=['GET'])
def innovation_get_rewards():
    """获取奖励列表API"""
    return get_rewards()

@innovation_bp.route('/api/exchange_reward', methods=['POST'])
def innovation_exchange_reward():
    """兑换奖励API"""
    return exchange_reward()

@innovation_bp.route('/api/get_point_records', methods=['GET'])
def innovation_get_point_records():
    """获取积分记录API"""
    return get_point_records()

@innovation_bp.route('/api/export_innovations', methods=['GET'])
def innovation_export_innovations():
    """导出创新项目API"""
    return export_innovations()

@innovation_bp.route('/api/get_statistics', methods=['GET'])
def innovation_get_statistics():
    """获取统计数据API"""
    return get_statistics()

@innovation_bp.route('/api/add_reward', methods=['POST'])
def innovation_add_reward():
    """添加奖励API"""
    return add_reward()

@innovation_bp.route('/api/upload_reward_image', methods=['POST'])
def innovation_upload_reward_image():
    """上传奖励图片API"""
    return upload_reward_image()

@innovation_bp.route('/api/update_reward', methods=['POST'])
def innovation_update_reward():
    """更新奖励API"""
    return update_reward()

@innovation_bp.route('/api/delete_reward', methods=['POST'])
def innovation_delete_reward():
    """删除奖励API"""
    return delete_reward()

@innovation_bp.route('/api/add_reward_with_image', methods=['POST'])
def innovation_add_reward_with_image():
    """添加带图片的奖励API"""
    return add_reward_with_image()

@innovation_bp.route('/uploads/<path:filename>')
def innovation_uploaded_file(filename):
    """上传文件访问"""
    return uploaded_file(filename)

@innovation_bp.route('/static/rewards/<filename>')
def innovation_reward_image(filename):
    """奖励图片访问"""
    return reward_image(filename)

@innovation_bp.route('/like_images/<path:filename>')
def innovation_like_image_file(filename):
    return like_image_file(filename)

@innovation_bp.route('/api/test_simple', methods=['GET'])
def innovation_test_simple():
    """简单测试API"""
    return test_simple()

@innovation_bp.route('/api/get_dashboard_data', methods=['GET'])
def innovation_get_dashboard_data():
    """获取仪表板数据API"""
    return get_dashboard_data()

@innovation_bp.route('/api/get_innovation_compare', methods=['GET'])
def innovation_get_innovation_compare():
    """获取相似提案对比数据API"""
    return get_innovation_compare()

@innovation_bp.route('/api/export_statistics', methods=['GET'])
def innovation_export_statistics():
    """导出统计数据API"""
    return export_statistics()

@innovation_bp.route('/api/react', methods=['POST'])
def innovation_bp_react():
    return innovation_react()

@innovation_bp.route('/api/react/comment', methods=['PUT'])
def innovation_bp_update_comment():
    return innovation_update_comment()

@innovation_bp.route('/api/react/stats', methods=['GET'])
def innovation_bp_get_react_stats():
    return innovation_get_react_stats()


@innovation_bp.route('/api/toggle_favorite', methods=['POST'])
def innovation_bp_toggle_favorite():
    return toggle_favorite()

@innovation_bp.route('/api/add_favorite_category', methods=['POST'])
def innovation_bp_add_favorite_category():
    return add_favorite_category()

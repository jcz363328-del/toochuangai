import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from secret_settings import env, get_feishu_company_configs


# 多公司飞书应用配置
FEISHU_CONFIGS = get_feishu_company_configs()

# 默认配置（向后兼容）
FEISHU_CONFIG = FEISHU_CONFIGS['company1']

# ... 其他配置保持不变 ...
# 数据库配置
DATABASE_PATH = 'innovation.db'

# 应用配置
DEFAULT_UPLOAD_FOLDER = r'D:\tuchuangai\创新图片'

APP_CONFIG = {
    'secret_key': env('INNOVATION_SECRET_KEY'),  # 请在 .env 中配置随机密钥
    'upload_folder': os.path.abspath(
        os.environ.get('INNOVATION_UPLOAD_FOLDER', DEFAULT_UPLOAD_FOLDER)
    ),
    'legacy_upload_folder': os.path.join(PROJECT_ROOT, 'uploads'),
    'export_folder': 'static/exports',
    'max_content_length': 512 * 1024 * 1024,  # 支持创新星主场视频上传
    'allowed_extensions': {'png', 'jpg', 'jpeg', 'gif'}
}

# 部门配置 - 更新为与飞书部门映射一致
DEPARTMENTS = [
    'TK项目',
    '总经办',
    '运营一部',
    '运营二部',
    '运营三部',
    '运营七部',
    '运营六部',
    '采购部',
    '研发部',
    '技术部',
    '视觉设计部',
    '摄影部',
    'AI部',
    '财务部',
    '人力行政部',
    '新人组',
    '仓储部',
    '深圳团队'
]

# 状态配置
STATUS_OPTIONS = [
    '待承接',
    '进行中',
    '已完成',
    '已取消',
    '已拒绝'
]

# 评分等级配置
SCORE_LEVELS = {
    'excellent': {'min': 9, 'max': 10, 'label': '优秀', 'color': 'success'},
    'good': {'min': 7, 'max': 8, 'label': '良好', 'color': 'primary'},
    'average': {'min': 4, 'max': 6, 'label': '一般', 'color': 'warning'},
    'poor': {'min': 1, 'max': 3, 'label': '较差', 'color': 'danger'},
    'none': {'min': 0, 'max': 0, 'label': '未评分', 'color': 'secondary'}
}

# 部门负责人映射（用于发送通知给部门负责人）
# 部门负责人映射（用于发送通知给部门负责人）
DEPARTMENT_FEISHU_MAPPING = {
    'TK项目': ['4a84e7cb','eg81a2ba'],
    'TK': ['4a84e7cb','eg81a2ba'],  # 兼容别名
    '总经办': '2bc94bde',
    '运营一部': 'b592dcdg',
    '运营二部': '83b87ea1',
    '运营三部': 'g2266f4g',
    '运营六部': '6gdd8597',
    '采购部': '49985db4',
    '研发部': 'c47a977b',
    '研发': 'c47a977b',  # 兼容别名
    '技术部': '9169ge99',
    '视觉设计部': 'e9f8bc94',
    '美工': 'e9f8bc94',  # 兼容别名
    '摄影部': 'd3ea2e18',
    '摄影': 'd3ea2e18',  # 兼容别名
    'AI部': ['c27449bd', 'c7ff44d1'],  # 支持多个接收者
    '数据': ['c27449bd', 'c7ff44d1'],
    '财务部': 'd76cdg26',
    '人力行政部': ['bc8d3629','b67ca328','c7ff44d1'],
    '人力': 'bc8d3629',  # 兼容别名
    '仓储部': '49985db4',
}

# 默认通知接收者（当部门没有负责人时使用）
DEFAULT_NOTIFICATION_RECEIVER = 'ou_4aa5b621905240b4a8dfee6628be8422'  # 人力行政部负责人

import requests
import json
import re
import threading
import time
import pytds
from functools import wraps
from flask import request, jsonify, session, redirect, url_for, has_request_context, g
from datetime import datetime, timedelta
import os
import hashlib
import hmac
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import binascii

from secret_settings import FEISHU_CONFIG as SECRET_FEISHU_CONFIG, sql_server_config
from tools import safe_print as _safe_print


# 飞书应用配置
FEISHU_CONFIG = dict(SECRET_FEISHU_CONFIG)

# 部门ID映射配置 - 硬编码部门ID和名称的对应关系，避免频繁API调用
DEPARTMENT_ID_MAPPING = {
    # 根据实际飞书组织架构配置部门ID和名称的映射关系
    # 格式: 'department_id': 'department_name'
    'od-f652a036dd421ff38d25b92e423026df': 'AI部',
    'od-82e136378bb07aeae74247dd78a08b18': 'TK直播部',
    'od-e7b5654df37bd9375225e8fce462a408': '财务部',
    'od-9929dd4f4d3b0be7c1f635d17e46ae22': '采购部',
    'od-692236b3673407d6c0333c42fd6b01af': '仓储部',
    'od-bca4e38e980226d367f7c501b3697e5a': '技术部',
    'od-c560effca33bf715c15f79a0670fe6ba': '内容生产工厂',
    'od-f400f2b1de53f7303b589420f14b6c5a': '人力行政部',
    'od-533088d36a43c281e0a2e99161e7e6a9': '摄影部',
    'od-c6530027bce19f79a623f46dc9a57372': '深圳团队',
    'od-791aa15d697bd40782942379363d4f21': '视觉设计部',
    'od-7f3fe0bc0e3d40946363a85b07e4c1c9': '外部顾问',
    'od-580f76720379d11ad66be30aaf7034a4': '新人组',
    'od-364835a9f7cc1ad050046cd995f886e4': '研发部',
    'od-9fca123ccde5fe9b2e8705d01365e754': '运营部',
    'od-44dc61c250f0246d8d91bb606828cc15': '总经办',
    'od-1fd573a06618d5efc50558aa4c6c8fde': 'BD部',
    'od-6fffe97f7129ad9bc85162ac5cabcb20': 'TK部门',
    'od-996da0561bdfe1bfb6ddb42adaa3b0e3': '产品&店铺运营',
    'od-85fabb3ca442f1f655e028732fda41b6': '独立站',
    'od-411009520c49cf4d96112d486356cacd': '短视频部',
    'od-3a5fdfc4a7c8a87f5f35b297dce74113': '客服',
    'od-98dc240d6d8d96f5dddcdc865adbbb03': '库管',
    'od-fc042116143e21654afa2dba4caf5d75': '人力行政',
    'od-8b20d4711c627f81b0bf8b72a0cc53fa': '文员',
    'od-b19ea8d2a8a9544921f0e437538f35e6': '沃尔玛',
    'od-3588e87a8fd07c8765285f3b95616fb4': '亚马逊',
    'od-89f78f0f72f3bfee4741b8aa1570b6c9': '运营二部',
    'od-e5024d4f6711f478ce052274d5ce33ea': '运营六部',
    'od-ee2a36f326f6cfad44ce06a80f2f07e8': '运营七部',
    'od-5ad4b6e18c3734622dbdae8ba05d27fd': '运营三部',
    'od-6d3c01c56d414c3b6ae96bc973b8ce70': '运营一部',
    'od-98541a1b5223e1166c4dfe456110bc34': '质检',
    'od-a96f3c9bcc41bf6e8d75ae7cf249c240': '桌长',
    'od-9eac17d59c51684f90a0a6c78ffe21ef': 'BD二组',
    'od-8e234df817e0707418b6fa50b1acd9c4': 'BD三组',
    'od-d98b885bdc8ee6cc33b62707404e8a43': 'BD四组',
    'od-884d568d0952416a876a77c087a1d15a': 'BD一组',
}

# 根部门权限按飞书父子部门链自动向下继承，无需逐个枚举子部门名称。
DEPARTMENT_TREE_INHERIT_ROOTS = {'内容生产工厂', '运营部'}
DEPARTMENT_TREE_INHERIT_EXCLUDED_DEPARTMENTS = {'新人组'}

# 权限配置 - 根据需求定义各功能模块的部门权限
PERMISSION_CONFIG = {
    # 全员可见的功能
    'innovation_proposals': {
        'name': '创新提案管理',
        'allowed_departments': 'all',  # 全员可见
        'description': '创新提案的提交、评审和管理系统'
    },
    'review_analysis': {
        'name': '差评分析系统',
        'allowed_departments': ['运营部', '研发部', '技术部', 'AI部', '总经办'],  # 运营部及其下各运营分部 + 研发部、技术部、AI部和总经办
        'description': '产品差评分析工具'
    },
    'amazon_reply_agent': {
        'name': '亚马逊站内信回复智能体',
        'allowed_departments': ['运营部', 'AI部', '总经办', '亚马逊'],
        'description': '根据亚马逊站内信生成合规英文回复，并支持规则与场景管理'
    },

    # 内容生产工厂功能
    'tk_email_register': {
        'name': '定时邮件',
        'allowed_departments': ['内容生产工厂','TK部门','TK直播部','BD部', '短视频部', '客服', '产品&店铺运营', 'AI部', '总经办','深圳团队', '技术部'],
        'description': '邮件定时发送功能'
    },
    'tk_video_realtime': {
        'name': '实时视频数据',
        'allowed_departments': ['内容生产工厂','TK部门','TK直播部','BD部', '短视频部', '客服', '产品&店铺运营', '摄影部', 'AI部', '总经办','财务部','深圳团队', '技术部'],
        'description': '按店铺/达人查看视频链接、标题、标签、时长、点赞/播放/评论/收藏/分享、抓取时间等数据'
    },
    'tk_dashboard': {
        'name': 'OKAYLOVE数据看板',
        'allowed_departments': ['内容生产工厂','TK部门','TK直播部', 'BD部', '短视频部', '客服', '产品&店铺运营', 'AI部', '总经办','财务部','深圳团队'],
        'description': '内容生产工厂86店数据看板'
    },
    'tk_total_dashboard': {
        'name': '数据看板汇总',
        'allowed_departments': ['内容生产工厂','TK部门','TK直播部', 'BD部', '短视频部', '客服', '产品&店铺运营', 'AI部', '总经办','财务部','深圳团队'],
        'description': '内容生产工厂整体数据看板'
    },
    'xiaotu_qa': {
        'name': '小图问答',
        'allowed_departments': 'all',
        'description': '云文档问答与分析助手'
    },
    'tk_customer_service': {
        'name': '客服',
        'allowed_departments': 'all',
        'description': '展示客服跟单信息，支持编辑并保存客服备注'
    },
    # 部门组功能卡片
    'tk_project_group': {
        'name': '内容生产工厂',
        'allowed_departments': ['内容生产工厂','TK部门','TK直播部', 'BD部', '短视频部', '客服', '产品&店铺运营', '新人组', 'AI部', '总经办','财务部','','亚马逊'],
        'description': '内容生产工厂专属功能模块'
    },
    'warehouse_group': {
        'name': '仓储部组功能',
        'allowed_departments': ['仓储部', '质检', '文员', '桌长', '库管', 'AI部', '总经办'],
        'description': '仓储部组专属功能模块'
    },

    # 独立部门功能卡片
    'general_office': {
        'name': '总经办功能',
        'allowed_departments': ['总经办', 'AI部'],
        'description': '总经办专属功能模块'
    },
    'operation_dept_1': {
        'name': '运营一部功能',
        'allowed_departments': ['运营一部', '新人组', 'AI部', '总经办'],
        'description': '运营一部专属功能模块'
    },
    'operation_dept_2': {
        'name': '运营二部功能',
        'allowed_departments': ['运营二部', '新人组', 'AI部', '总经办'],
        'description': '运营二部专属功能模块'
    },
    'operation_dept_3': {
        'name': '运营三部功能',
        'allowed_departments': ['运营三部', '新人组', 'AI部', '总经办'],
        'description': '运营三部专属功能模块'
    },
    'operation_dept_6': {
        'name': '运营六部功能',
        'allowed_departments': ['运营六部', '新人组', 'AI部', '总经办'],
        'description': '运营六部专属功能模块'
    },
    'operation_dept_7': {
        'name': '运营七部功能',
        'allowed_departments': ['运营七部', '新人组', 'AI部', '总经办'],
        'description': '运营七部专属功能模块'
    },
    'procurement_dept': {
        'name': '采购部功能',
        'allowed_departments': ['采购部', 'AI部', '总经办'],
        'description': '采购部专属功能模块'
    },
    'rd_dept': {
        'name': '研发部功能',
        'allowed_departments': ['研发部', 'AI部', '总经办'],
        'description': '研发部专属功能模块'
    },
    'tech_dept': {
        'name': '技术部功能',
        'allowed_departments': ['技术部', 'AI部', '总经办'],
        'description': '技术部专属功能模块'
    },
    'visual_design_dept': {
        'name': '视觉设计部功能',
        'allowed_departments': 'all',
        'description': '视觉设计部功能模块（全员可见）'
    },
    'photography_dept': {
        'name': '摄影部功能',
        'allowed_departments': ['摄影部', 'AI部', '总经办'],
        'description': '摄影部专属功能模块'
    },
    'ai_dept': {
        'name': 'AI部功能',
        'allowed_departments': ['AI部', '总经办'],
        'description': 'AI部专属功能模块'
    },
    'daily_replenishment': {
        'name': '日常补货',
        'allowed_departments': ['AI部'],
        'description': 'AI功能卡片中的日常补货工作台，仅允许 AI部访问'
    },
    'daily_replenishment_operation': {
        'name': '智能补货中心-运营',
        'allowed_departments': ['运营部', 'AI部', '总经办'],
        'description': '智能补货中心-运营版多工作表刷新功能，运营人员按 v_PinPaiDianPu.YunYing 查看本人店铺'
    },
    'ai_group_performance': {
        'name': '组别经营数据',
        'allowed_departments': ['AI部'],
        'description': '按月份和组别查询店铺及站点经营数据，仅允许 AI部访问'
    },
    'video_claw': {
        'name': 'VideoClaw AI视频创作',
        'allowed_departments': ['AI部'],
        'description': 'VideoClaw 全流程 AI 视频创作工作台，仅允许 AI部访问'
    },
    'finance_dept': {
        'name': '财务部功能',
        'allowed_departments': ['财务部', 'AI部', '总经办'],
        'description': '财务部专属功能模块'
    },
    'hr_admin_dept': {
        'name': '人力行政部功能',
        'allowed_departments': ['人力行政部', 'AI部', '总经办'],
        'description': '人力行政部专属功能模块'
    },
    'newcomer_group': {
        'name': '新人组功能',
        'allowed_departments': ['新人组', 'AI部', '总经办'],
        'description': '新人组专属功能模块'
    },
    'shenzhen_dept': {
        'name': '深圳功能模块',
        'allowed_departments': ['深圳团队', '总经办', 'AI部', '亚马逊'],
        'description': '深圳团队专属功能模块'
    },

    # 保留原有的特定功能（向后兼容）
    'script_generator': {
        'name': '脚本生成器',
        'allowed_departments': ['BD部', 'TK部门', 'TK直播部', '短视频部', 'AI部', '总经办','深圳团队'],  # 内容生产工厂的短视频和BD部门 + AI部和总经办
        'description': '基于AI营销脚本生成工具'
    },
    'influencer_management': {
        'name': 'TK达人管理',
        'allowed_departments': ['BD部', 'TK部门', 'TK直播部', '短视频部', 'AI部', '总经办','深圳团队'],  # 内容生产工厂的短视频和BD部门 + AI部和总经办
        'description': 'TikTok达人信息管理系统'
    },
    'model_library': {
        'name': '模特库管理',
        'allowed_departments': ['技术部', 'AI部', '总经办'],
        'description': '模特信息管理与视频上传'
    },
    'model_queue': {
        'name': '模特排队',
        'allowed_departments': 'all',
        'description': '模特排队与视频完成管理'
    },
    'admin_functions': {
        'name': '管理员功能',
        'allowed_departments': ['总经办', 'AI部'],
        'description': '系统管理和高级功能'
    },
    'performance_monitor': {
        'name': '性能监控',
        'allowed_departments': ['AI部', '总经办'],
        'description': '查看系统性能和缓存状态，监控系统运行情况和资源使用情况'
    }
}

OPERATION_CARD_OVERRIDE_USERS = {'孙洁', '侯梁'}
OPERATION_CARD_OVERRIDE_FUNCTIONS = [
    'operation_dept_1',
    'operation_dept_2',
    'operation_dept_3',
    'operation_dept_6',
    'operation_dept_7',
]

# 通讯录尚未同步到新部门时，保证指定人员可以进入对应部门卡片。
USER_FUNCTION_OVERRIDES = {
    '赵瑜': ['operation_dept_7'],
}

# ==========================
# 开发者配置 - 用于调试模式
# ==========================
DEVELOPER_CONFIG = {
    'enabled': True,  # 是否启用开发者模式（True 表示启用，False 表示关闭）
    'developer_emails': ['developer@company.com'],  # 开发者邮箱列表，用于识别哪些用户是开发者
    'developer_user_ids': ['ou_developer_id'],  # 开发者飞书用户 ID 列表
    'bypass_all_permissions': True  # 是否绕过权限检查（开发者模式下常用，避免频繁调试权限逻辑）
}

# ==========================
# 性能优化配置
# ==========================
PERFORMANCE_CONFIG = {
    'use_api_fallback': True,  # 为新部门启用 API 回退，避免未写入映射表时权限卡片不显示
    # 下面是配置的描述信息（多行拼接字符串）
    'description': '当部门映射表中找不到部门时，是否回退到API调用获取部门信息。'
                  '设置为False可避免16个部门的逐一API查询，大幅提升权限检查速度。'
                  '建议将所有部门添加到DEPARTMENT_ID_MAPPING映射表中，然后禁用API回退。'
}

# ==========================
# 飞书权限管理类
# ==========================
class FeishuPermissionManager:
    def __init__(self):
        # 从全局配置 FEISHU_CONFIG 中读取飞书应用的关键信息
        self.app_id = FEISHU_CONFIG['app_id']  # 飞书应用 ID
        self.app_secret = FEISHU_CONFIG['app_secret']  # 飞书应用 Secret
        self.encrypt_key = FEISHU_CONFIG.get('encrypt_key', '')  # 加密 key（可选，没有则为空字符串）
        self.verification_token = FEISHU_CONFIG.get('verification_token', '')  # 验证 token（可选，没有则为空字符串）
        self.access_token = None  # 当前存储的 access_token
        self.token_expires_at = None  # access_token 过期时间

        # ==========================
        # 缓存机制
        # ==========================
        self._user_departments_cache = {}  # 用户部门信息缓存，key=用户ID，value=部门信息
        self._department_info_cache = {}   # 部门详情缓存，key=部门ID，value=部门信息
        self._user_info_cache = {}         # 用户基本信息缓存，key=用户ID，value=用户信息
        self._cache_expire_time = 300      # 缓存过期时间，单位秒（这里设置为5分钟）
        self._permission_rows_cache = None
        self._permission_rows_cached_at = 0.0
        self._permission_rows_cache_ttl = 30
        self._permission_rows_lock = threading.Lock()
        self._user_permission_overrides_cache = {}
        self._permission_override_storage_ready = False
        self._permission_override_storage_lock = threading.Lock()
        self._direct_http = requests.Session()
        self._direct_http.trust_env = False

    def _feishu_request(self, method, url, **kwargs):
        # 飞书或代理异常时不能让页面请求无限等待；调用方仍可传入更短的超时。
        kwargs.setdefault('timeout', 8)
        try:
            return requests.request(method=method, url=url, **kwargs)
        except requests.exceptions.ProxyError as e:
            _safe_print(f"⚠️ 代理连接失败，切换直连重试: {e}")
            return self._direct_http.request(method=method, url=url, **kwargs)

    def clear_cache(self, user_id=None):
        """清理缓存"""
        # 权限表可能被管理页随时更新，无论清理单个用户还是全部缓存，
        # 都要让下一次校验重新读取 dbo.quanxian。
        self._permission_rows_cache = None
        self._permission_rows_cached_at = 0.0
        if user_id:
            # 如果传入 user_id，则只清理该用户的缓存
            if user_id in self._user_departments_cache:
                del self._user_departments_cache[user_id]  # 删除该用户的部门缓存
                _safe_print(f"🧹 已清理用户 {user_id} 的部门缓存")
            self._user_permission_overrides_cache.pop(str(user_id), None)
        else:
            # 如果没有传入 user_id，则清理所有缓存（全局清空）
            self._user_departments_cache.clear()
            self._department_info_cache.clear()
            self._user_info_cache.clear()
            self._user_permission_overrides_cache.clear()
            self.access_token = None  # 同时清空 access_token
            self.token_expires_at = None  # 清空 token 过期时间
            _safe_print("🧹 已清理所有缓存")

    def get_cache_stats(self):
        """获取缓存统计信息"""
        from datetime import datetime

        # 统计缓存的总数量
        user_cache_count = len(self._user_departments_cache)  # 用户部门缓存数量
        dept_cache_count = len(self._department_info_cache)   # 部门缓存数量
        user_info_cache_count = len(self._user_info_cache)    # 用户信息缓存数量

        # 有效缓存数量统计
        valid_user_cache = 0
        valid_dept_cache = 0
        valid_user_info_cache = 0

        # 遍历用户部门缓存，检查是否过期
        for cache_data in self._user_departments_cache.values():
            if datetime.now() < cache_data['expire_time']:  # 如果未过期
                valid_user_cache += 1

        # 遍历部门缓存，检查是否过期
        for cache_data in self._department_info_cache.values():
            if datetime.now() < cache_data['expire_time']:  # 如果未过期
                valid_dept_cache += 1

        # 检查用户信息缓存是否过期
        import time
        current_time = time.time()  # 当前时间戳（秒）
        for cached_data, cache_time in self._user_info_cache.values():
            if current_time - cache_time < self._cache_expire_time:  # 如果缓存未过期
                valid_user_info_cache += 1

        # 返回一个字典，包含缓存的总数与有效数量
        return {
            'user_departments_cache': {'total': user_cache_count, 'valid': valid_user_cache},
            'department_info_cache': {'total': dept_cache_count, 'valid': valid_dept_cache},
            'user_info_cache': {'total': user_info_cache_count, 'valid': valid_user_info_cache},
            'access_token_cached': self.access_token is not None,  # access_token 是否已缓存
            'hardcoded_departments_count': len(DEPARTMENT_ID_MAPPING)  # 硬编码的部门数量
        }

    def get_department_mapping_stats(self):
        """获取部门映射统计信息"""
        return {
            'total_mapped_departments': len(DEPARTMENT_ID_MAPPING),  # 部门映射的总数
            'department_list': list(DEPARTMENT_ID_MAPPING.values()),  # 所有部门的列表
            'mapping_config': DEPARTMENT_ID_MAPPING  # 完整的映射配置
        }

    def suggest_department_mapping_update(self, dept_id, dept_name):
        """建议更新部门映射配置"""
        if dept_id not in DEPARTMENT_ID_MAPPING:
            # 如果 dept_id 不在部门映射表中，建议添加该部门映射
            suggestion = f"# 建议添加到DEPARTMENT_ID_MAPPING:\n'{dept_id}': '{dept_name}',"
            _safe_print(f"\n💡 部门映射更新建议:")
            _safe_print(suggestion)  # 打印建议内容
            return suggestion  # 返回建议字符串
        return None  # 如果 dept_id 已存在于映射中，则返回 None

    def validate_department_mapping(self):
        """验证部门映射配置的有效性"""
        _safe_print(f"\n🔍 验证部门映射配置...")
        _safe_print(f"📊 当前映射的部门数量: {len(DEPARTMENT_ID_MAPPING)}")

        invalid_mappings = []  # 用于存储无效的部门映射
        valid_mappings = []  # 用于存储有效的部门映射

        for dept_id, dept_name in DEPARTMENT_ID_MAPPING.items():
            # 验证部门 ID 是否有效，检查格式（如：是否以 'od-' 开头，长度大于10等）
            if dept_id.startswith('od-') and len(dept_id) > 10 and dept_name.strip():
                valid_mappings.append((dept_id, dept_name))  # 如果有效，加入有效列表
            else:
                invalid_mappings.append((dept_id, dept_name))  # 否则加入无效列表

        _safe_print(f"✅ 有效映射: {len(valid_mappings)}个")
        if invalid_mappings:
            _safe_print(f"⚠️ 可能无效的映射: {len(invalid_mappings)}个")
            for dept_id, dept_name in invalid_mappings:
                _safe_print(f"  - {dept_id}: {dept_name}")  # 打印出无效的部门映射

        # 返回验证结果
        return {
            'valid_count': len(valid_mappings),  # 有效映射数量
            'invalid_count': len(invalid_mappings),  # 无效映射数量
            'valid_mappings': valid_mappings,  # 有效映射列表
            'invalid_mappings': invalid_mappings  # 无效映射列表
        }

    def verify_feishu_request(self, timestamp, nonce, body, signature):
        """验证飞书回调请求的合法性"""
        try:
            # 检查是否有encrypt_key配置
            if not self.encrypt_key:
                _safe_print("⚠️ encrypt_key未配置，跳过签名验证")
                return True  # 如果没有encrypt_key，跳过验证，直接认为合法

            # 构建待签名字符串
            string_to_sign = f"{timestamp}{nonce}{self.encrypt_key}{body}"

            # 使用HMAC-SHA256计算签名
            expected_signature = hmac.new(
                self.encrypt_key.encode('utf-8'),  # 使用 encrypt_key 作为密钥
                string_to_sign.encode('utf-8'),  # 将待签名的字符串编码成字节
                hashlib.sha256  # 使用 SHA256 算法
            ).hexdigest()  # 获取签名的十六进制表示

            _safe_print(f"🔐 飞书请求验证:")
            _safe_print(f"  时间戳: {timestamp}")
            _safe_print(f"  随机数: {nonce}")
            _safe_print(f"  请求体: {body[:100]}..." if len(body) > 100 else f"  请求体: {body}")
            _safe_print(f"  收到签名: {signature}")
            _safe_print(f"  期望签名: {expected_signature}")
            _safe_print(f"  验证结果: {'✅ 通过' if signature == expected_signature else '❌ 失败'}")

            # 如果收到的签名与计算的签名一致，验证通过
            return signature == expected_signature

        except Exception as e:
            _safe_print(f"❌ 验证飞书请求异常: {e}")
            return False  # 如果发生异常，认为验证失败

    def decrypt_feishu_data(self, encrypted_data):
        """解密飞书加密数据"""
        try:
            # 检查是否有encrypt_key配置
            if not self.encrypt_key:
                _safe_print("⚠️ encrypt_key未配置，无法解密数据，返回原始数据")
                return encrypted_data  # 如果没有encrypt_key，返回原始数据

            _safe_print(f"🔐 开始解密飞书数据...")
            _safe_print(f"加密数据: {encrypted_data[:50]}...")

            # Base64解码
            encrypted_bytes = base64.b64decode(encrypted_data)
            _safe_print(f"解码后长度: {len(encrypted_bytes)}")

            # 生成密钥 (SHA-256)
            key = hashlib.sha256(self.encrypt_key.encode('utf-8')).digest()
            _safe_print(f"密钥长度: {len(key)}")

            # 提取IV (前16字节)
            iv = encrypted_bytes[:16]
            _safe_print(f"IV: {binascii.hexlify(iv).decode()}")

            # 提取加密数据 (16字节后的所有数据)
            encrypted_content = encrypted_bytes[16:]
            _safe_print(f"加密内容长度: {len(encrypted_content)}")

            # AES解密 - 使用NOPADDING模式（飞书官方要求）
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend

            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            decrypted_bytes = decryptor.update(encrypted_content) + decryptor.finalize()

            # 调试：打印解密后的原始字节
            _safe_print(f"解密后原始字节（前20字节）: {decrypted_bytes[:20]}")
            _safe_print(f"解密后原始字节（十六进制）: {binascii.hexlify(decrypted_bytes[:50]).decode()}")

            # 飞书官方填充处理逻辑
            # 参考：https://blog.csdn.net/weixin_40514790/article/details/117820382
            if len(decrypted_bytes) > 0:
                p = len(decrypted_bytes) - 1
                _safe_print(f"开始填充处理，数据长度: {len(decrypted_bytes)}")
                _safe_print(f"末尾10字节: {decrypted_bytes[-10:]}")

                # 飞书的填充处理：从末尾开始，找到第一个大于16的字节
                while p >= 0 and decrypted_bytes[p] <= 16:
                    _safe_print(f"位置 {p}: 字节值 {decrypted_bytes[p]} <= 16")
                    p -= 1

                _safe_print(f"填充处理结束，p = {p}, 原长度 = {len(decrypted_bytes)}")

                if p != len(decrypted_bytes) - 1:
                    # 截取到有效数据的结束位置
                    decrypted_bytes = decrypted_bytes[:p + 1]
                    _safe_print(f"✅ 飞书填充处理完成，有效数据长度: {len(decrypted_bytes)}")
                else:
                    _safe_print(f"⚠️ 未发现填充，保持原始数据长度: {len(decrypted_bytes)}")

            # 转换为字符串
            try:
                decrypted_text = decrypted_bytes.decode('utf-8')
                _safe_print(f"✅ 解密成功: {decrypted_text[:100]}...")
            except UnicodeDecodeError as e:
                _safe_print(f"UTF-8解码失败: {e}")
                # 解密失败，抛出异常让上层处理
                _safe_print(f"⚠️ 解密失败，可能是密钥不正确")
                raise Exception(f"解密失败: {e}")

            return decrypted_text

        except Exception as e:
            _safe_print(f"❌ 解密飞书数据异常: {e}")
            import traceback
            _safe_print(f"🔍 错误详情: {traceback.format_exc()}")
            raise e

    def get_user_info_from_feishu_context(self):
        """从飞书上下文中获取用户信息（仅认当前应用 user_access_token）"""
        try:
            # 打印所有请求头信息用于调试
            _safe_print("\n=== 飞书上下文调试信息 ===")
            _safe_print(f"请求URL: {request.url}")  # 打印当前请求的 URL
            _safe_print(f"请求方法: {request.method}")  # 打印请求方法（GET/POST等）
            _safe_print(f"User-Agent: {request.headers.get('User-Agent', 'N/A')}")  # 打印 User-Agent，标识请求来源的客户端

            # 打印所有可能的飞书相关请求头
            feishu_headers = {
                'X-Lark-User-Id': request.headers.get('X-Lark-User-Id'),  # 用户 ID
                'X-Lark-User-Access-Token': request.headers.get('X-Lark-User-Access-Token'),  # 用户访问 token
                'X-Lark-Open-Id': request.headers.get('X-Lark-Open-Id'),  # Open ID
                'X-Lark-Union-Id': request.headers.get('X-Lark-Union-Id'),  # Union ID
                'X-Plugin-Token': request.headers.get('X-Plugin-Token'),  # 插件 token
                'X-User-Plugin-Token': request.headers.get('X-User-Plugin-Token'),  # 用户插件 token
                'Authorization': request.headers.get('Authorization'),  # 授权头信息
                'X-Forwarded-For': request.headers.get('X-Forwarded-For'),  # 转发的原始 IP
                'X-Real-IP': request.headers.get('X-Real-IP')  # 实际 IP
            }

            _safe_print("飞书相关请求头:")  # 打印飞书相关的所有请求头
            for header, value in feishu_headers.items():
                if value:
                    _safe_print(f"  {header}: {value}")  # 如果请求头存在，打印其值
                else:
                    _safe_print(f"  {header}: [未找到]")  # 如果请求头不存在，提示未找到

            # 统一只认当前应用的 user_access_token，避免不同应用/旧会话串号
            user_id = request.headers.get('X-Lark-User-Id')
            user_token = request.headers.get('X-Lark-User-Access-Token')
            if not user_token:
                auth_header = str(request.headers.get('Authorization') or '').strip()
                if auth_header.lower().startswith('bearer '):
                    user_token = auth_header[7:].strip()
            open_id = request.headers.get('X-Lark-Open-Id')
            union_id = request.headers.get('X-Lark-Union-Id')

            _safe_print(f"\n🔍 飞书身份信息解析:")
            _safe_print(f"  User ID: {user_id}")  # 打印获取的 User ID
            _safe_print(f"  Open ID: {open_id}")  # 打印获取的 Open ID
            _safe_print(f"  Union ID: {union_id}")  # 打印获取的 Union ID
            _safe_print(f"  Token存在: {bool(user_token)}")  # 打印用户 token 是否存在
            _safe_print("========================\n")

            if user_token:
                _safe_print(f"✅ 检测到用户Token，尝试通过Token获取用户信息")  # 如果检测到 token，尝试通过 token 获取用户信息
                token_info = self.get_user_info_by_token(user_token)
                if isinstance(token_info, dict):
                    token_info = dict(token_info)
                    if not token_info.get('user_id'):
                        token_info['user_id'] = token_info.get('open_id') or user_id or open_id
                    if not token_info.get('open_id') and open_id:
                        token_info['open_id'] = open_id
                    if not token_info.get('name'):
                        token_info['name'] = '飞书用户'
                    if not token_info.get('email'):
                        token_info['email'] = f'{(open_id or user_id or "unknown")}@feishu.com'
                    return token_info
                _safe_print("❌ user_access_token 存在，但未取到当前应用下的有效用户信息")
                return None
            _safe_print("❌ 未检测到当前应用可用的 user_access_token")  # 如果没有token，直接返回 None
            return None

        except Exception as e:
            _safe_print(f"❌ 获取飞书上下文用户信息异常: {e}")  # 如果发生异常，打印错误信息
            import traceback
            _safe_print(traceback.format_exc())  # 打印异常的详细信息
            return None  # 返回 None，表示获取用户信息失败

    def get_access_token(self):
        """获取飞书访问令牌（带缓存）"""
        # 检查token是否还有效
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            _safe_print(f"✅ 使用缓存的访问令牌: {self.access_token[:20]}...")
            return self.access_token  # 如果缓存的token有效，直接返回缓存的访问令牌

        _safe_print(f"🔄 获取新的访问令牌...")
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"  # 飞书API获取令牌的URL
        headers = {
            "Content-Type": "application/json; charset=utf-8"  # 请求头，指定Content-Type
        }
        data = {
            "app_id": self.app_id,  # 应用ID
            "app_secret": self.app_secret  # 应用密钥
        }

        try:
            # 发送请求获取access_token
            response = self._feishu_request("POST", url, headers=headers, json=data, timeout=10)  # POST 请求
            result = response.json()  # 获取响应结果

            if result.get('code') == 0:
                self.access_token = result['tenant_access_token']  # 获取新的访问令牌
                # 设置token过期时间（提前5分钟刷新）
                expires_in = result.get('expire', 7200) - 300  # 默认过期时间7200秒，减去5分钟
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)  # 设置过期时间
                _safe_print(f"✅ 新访问令牌获取成功，有效期至: {self.token_expires_at}")
                return self.access_token  # 返回新的 access_token
            else:
                _safe_print(f"❌ 获取飞书access_token失败: {result}")  # 如果获取失败，打印错误信息
                return None  # 返回 None 表示获取失败
        except Exception as e:
            _safe_print(f"❌ 获取飞书access_token异常: {e}")  # 捕获异常并输出错误
            return None  # 返回 None 表示异常

    def get_user_info_by_code(self, code):
        """通过授权码获取用户信息"""
        _safe_print(f"\n=== 通过授权码获取用户信息 ===")
        _safe_print(f"🔑 授权码已收到: {bool(code)}")

        # 新版 OAuth 授权码换取 user_access_token（v2）
        url = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
        redirect_uri = FEISHU_CONFIG['production_domain'] + FEISHU_CONFIG['callback_path']
        headers = {
            "Content-Type": "application/json; charset=utf-8"  # 请求头，指定 Content-Type
        }
        data = {
            "grant_type": "authorization_code",  # 授权类型
            "code": code,  # 授权码
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "redirect_uri": redirect_uri
        }

        _safe_print(f"🌐 请求URL: {url}")  # 打印请求的 URL
        _safe_print(f"📋 请求头: {headers}")  # 打印请求头
        _safe_print(
            f"📦 请求数据: grant_type={data.get('grant_type')}, "
            f"client_id={data.get('client_id')}, redirect_uri={data.get('redirect_uri')}"
        )

        try:
            _safe_print(f"🚀 发送请求获取用户访问令牌...")
            response = self._feishu_request("POST", url, headers=headers, json=data, timeout=10)  # 发送请求
            _safe_print(f"📊 响应状态码: {response.status_code}")  # 打印响应的状态码
            _safe_print(f"📄 响应头: {dict(response.headers)}")  # 打印响应头
            result = response.json()  # 获取响应结果
            _safe_print(
                f"📋 响应概要: code={result.get('code')}, "
                f"token_present={bool(result.get('access_token') or result.get('user_access_token') or (result.get('data') or {}).get('access_token'))}"
            )

            if result.get('code') == 0:
                token_data = result.get('data') or result
                user_access_token = (
                    result.get('access_token')
                    or result.get('user_access_token')
                    or token_data.get('access_token')
                    or token_data.get('user_access_token')
                )  # 获取用户访问令牌
                if not user_access_token:
                    _safe_print(f"❌ 响应成功但未返回 user_access_token")
                    _safe_print("========================\n")
                    return None
                _safe_print(f"✅ 用户访问令牌获取成功: length={len(user_access_token)}")
                _safe_print(f"🔄 开始通过用户令牌获取用户信息...")
                user_info = self.get_user_info_by_token(user_access_token)  # 使用用户 token 获取用户信息
                if isinstance(user_info, dict):
                    user_info['user_access_token'] = user_access_token
                    user_info['user_refresh_token'] = token_data.get('refresh_token', '')
                    user_info['user_token_expires_in'] = token_data.get('expires_in', 0)
                    user_info['user_refresh_expires_in'] = token_data.get('refresh_expires_in', 0)
                _safe_print(
                    "📋 最终用户信息: "
                    f"name={(user_info or {}).get('name') if isinstance(user_info, dict) else ''}, "
                    f"open_id={(user_info or {}).get('open_id') if isinstance(user_info, dict) else ''}"
                )
                _safe_print("========================\n")
                return user_info  # 返回用户信息
            else:
                _safe_print(f"❌ 通过code获取用户token失败")  # 如果失败，打印失败信息
                _safe_print(f"🔍 错误代码: {result.get('code')}")  # 打印错误代码
                _safe_print(f"🔍 错误消息: {result.get('msg')}")  # 打印错误消息
                _safe_print(f"🔍 响应概要: code={result.get('code')}, msg={result.get('msg')}")
                _safe_print("========================\n")
                return None  # 如果获取失败，返回 None
        except requests.exceptions.Timeout:
            _safe_print(f"❌ 请求超时（10秒）")  # 请求超时的异常处理
            _safe_print("========================\n")
            return None  # 返回 None 表示请求超时
        except requests.exceptions.RequestException as e:
            _safe_print(f"❌ 网络请求异常: {e}")  # 网络请求异常的处理
            _safe_print("========================\n")
            return None  # 返回 None 表示发生了网络异常
        except Exception as e:
            _safe_print(f"❌ 通过code获取用户信息异常: {e}")  # 捕获其他异常并输出
            import traceback
            _safe_print(f"🔍 异常详情: {traceback.format_exc()}")  # 打印异常的详细信息
            _safe_print("========================\n")
            return None  # 返回 None 表示获取用户信息失败

    def get_user_info_by_token(self, user_access_token):
        """通过用户token获取用户信息（带缓存）"""
        import time

        # 检查缓存
        token_text = str(user_access_token or '')
        token_hash = hashlib.sha256(token_text.encode('utf-8')).hexdigest()
        cache_key = f"user_token_{token_hash}"  # 使用完整token哈希作为缓存键，避免不同用户token前缀冲突
        current_time = time.time()  # 获取当前时间（时间戳）

        # 检查缓存中是否已经有该token的信息
        if cache_key in self._user_info_cache:
            cached_data, cache_time = self._user_info_cache[cache_key]  # 从缓存中取出数据和缓存时间
            if current_time - cache_time < self._cache_expire_time:  # 如果缓存未过期
                _safe_print(f"[缓存命中] 用户token信息")  # 打印缓存命中的信息
                return cached_data  # 返回缓存的用户信息

        _safe_print(f"[API调用] 通过token获取用户信息")  # 如果缓存中没有，进行 API 调用
        url = "https://open.feishu.cn/open-apis/authen/v1/user_info"  # 获取用户信息的API URL
        headers = {
            "Authorization": f"Bearer {user_access_token}",  # 使用用户token进行授权
            "Content-Type": "application/json; charset=utf-8"  # 请求头
        }

        try:
            response = self._feishu_request("GET", url, headers=headers, timeout=10)  # 发送GET请求
            result = response.json()  # 获取响应结果

            if result.get('code') == 0:  # 如果返回的code是0，表示请求成功
                user_info = result['data']  # 获取用户信息
                # 缓存结果
                self._user_info_cache[cache_key] = (user_info, current_time)  # 缓存用户信息及当前时间
                return user_info  # 返回用户信息
            else:
                _safe_print(f"❌ 获取用户信息失败: {result}")  # 如果获取失败，打印错误信息
                return None  # 返回None表示获取失败
        except Exception as e:
            _safe_print(f"❌ 获取用户信息异常: {e}")  # 捕获异常并输出错误信息
            return None  # 返回None表示发生异常

    def get_user_departments(self, user_id):
        """获取用户所属部门信息（带缓存）"""
        from datetime import datetime, timedelta

        # 本地调试账号仍按 session 中模拟部门走同一张 quanxian 表，不再走硬编码权限分支。
        if str(user_id or "").startswith("dev_") and has_request_context():
            department_name = str(session.get("user_department") or "").strip()
            if department_name:
                return [{
                    "department_id": f"local:{department_name}",
                    "name": department_name,
                    "status": "active",
                    "source": "local_dev_session",
                }]

        # 检查缓存
        cache_key = user_id  # 使用用户ID作为缓存的键
        if cache_key in self._user_departments_cache:
            cache_data = self._user_departments_cache[cache_key]  # 获取缓存数据
            if datetime.now() < cache_data['expire_time']:  # 如果缓存未过期
                _safe_print(f"📋 使用缓存的用户部门信息: {len(cache_data['data'])}个部门")
                return cache_data['data']  # 返回缓存的部门信息

        _safe_print(f"\n=== 获取用户部门信息 ===")
        _safe_print(f"🔍 目标用户ID: {user_id}")  # 打印目标用户ID

        # 获取访问令牌
        _safe_print(f"🔑 正在获取访问令牌...")
        token = self.get_access_token()  # 获取访问令牌
        if not token:
            _safe_print("❌ 无法获取访问令牌，部门信息获取失败")  # 如果无法获取令牌，返回失败
            _safe_print("========================\n")
            return []
        _safe_print(f"✅ 访问令牌获取成功: length={len(token)}")

        url = f"https://open.feishu.cn/open-apis/contact/v3/users/{user_id}"  # 获取用户部门信息的 API URL
        headers = {
            "Authorization": f"Bearer {token}",  # 使用获取的 token 进行授权
            "Content-Type": "application/json; charset=utf-8"  # 请求头
        }
        user_id_type = 'open_id' if str(user_id).startswith('ou_') else 'user_id'
        # 后续部门树继承使用 open_department_id 追溯父级，
        # 这里必须要求用户接口返回同一类型的部门 ID。
        params = {
            "user_id_type": user_id_type,
            "department_id_type": "open_department_id",
        }

        _safe_print(f"📡 请求飞书API:")  # 打印请求的 API 信息
        _safe_print(f"  URL: {url}")
        _safe_print("  Headers: Authorization=<redacted>, Content-Type=application/json")
        _safe_print(f"  Params: {params}")

        try:
            _safe_print(f"🌐 发送HTTP请求...")
            response = self._feishu_request("GET", url, headers=headers, params=params, timeout=10)  # 发送 GET 请求
            _safe_print(f"📊 HTTP状态码: {response.status_code}")  # 打印 HTTP 状态码

            result = response.json()  # 获取响应的 JSON 数据
            _safe_print(f"📥 飞书API完整响应:")
            _safe_print(f"  Code: {result.get('code')}")
            _safe_print(f"  Message: {result.get('msg')}")
            _safe_print(f"  Data: {result.get('data')}")

            if result.get('code') == 0:  # 如果返回的 code 是 0，表示请求成功
                user_data = result['data']['user']  # 获取用户数据
                department_ids = user_data.get('department_ids', [])  # 获取用户所属部门ID列表
                _safe_print(f"📋 解析结果:")
                _safe_print(f"  用户所属部门ID列表: {department_ids}")
                _safe_print(f"  用户其他信息: name={user_data.get('name')}, email={user_data.get('email')}")

                # 使用硬编码的部门映射获取部门详细信息（性能优化）
                departments = []  # 存储用户的部门信息
                _safe_print(f"\n🏢 使用硬编码映射获取部门信息（性能优化）:")

                # 性能优化：优先使用映射表，避免API调用
                use_api_fallback = PERFORMANCE_CONFIG['use_api_fallback']  # 从全局配置读取是否启用API回退

                for i, dept_id in enumerate(department_ids, 1):  # 遍历所有部门ID
                    _safe_print(f"  [{i}/{len(department_ids)}] 处理部门 {dept_id}...")

                    # 从硬编码映射中获取部门名称
                    dept_name = DEPARTMENT_ID_MAPPING.get(dept_id)

                    if dept_name:
                        dept_info = {
                            'department_id': dept_id,
                            'name': dept_name,
                            'status': 'active',  # 标记为有效部门
                            'source': 'hardcoded_mapping'  # 来源于硬编码的映射
                        }
                        departments.append(dept_info)
                        _safe_print(f"    ✅ 映射成功: {dept_name} (ID: {dept_id})")
                    else:
                        if use_api_fallback:
                            # 如果映射中没有找到，回退到API调用（可选）
                            _safe_print(f"    ⚠️ 映射中未找到部门 {dept_id}，回退到API调用...")
                            dept_info = self.get_department_info(dept_id)  # 通过API获取部门信息
                            if dept_info:
                                # 飞书部门详情在 open_department_id 模式下通常只返回
                                # open_department_id。权限继承内部统一使用 department_id，
                                # 因此必须在这里规范化，否则未硬编码的多层子部门会无法追溯父级。
                                normalized_dept_info = dict(dept_info)
                                normalized_dept_info['department_id'] = str(
                                    normalized_dept_info.get('open_department_id')
                                    or dept_id
                                    or normalized_dept_info.get('department_id')
                                ).strip()
                                normalized_dept_info.setdefault('source', 'api_fallback')
                                departments.append(normalized_dept_info)
                                _safe_print(f"    ✅ API调用成功: {normalized_dept_info}")
                                # 自动生成映射更新建议
                                self.suggest_department_mapping_update(dept_id, dept_info.get('name', '未知部门'))
                            else:
                                _safe_print(f"    ❌ API调用也失败: 无法获取部门 {dept_id} 信息")
                                # 创建一个标记为无效的部门信息
                                invalid_dept = {
                                    'department_id': dept_id,
                                    'name': '未知部门',
                                    'status': 'invalid',
                                    'error': '部门映射和API调用均失败'
                                }
                                departments.append(invalid_dept)
                        else:
                            # 性能优化：直接跳过未映射的部门，避免API调用
                            _safe_print(f"    ⚠️ 映射中未找到部门 {dept_id}，跳过API调用（性能优化）")
                            _safe_print(f"    💡 建议将部门 {dept_id} 添加到DEPARTMENT_ID_MAPPING映射表中")
                            # 创建一个标记为未映射的部门信息
                            unmapped_dept = {
                                'department_id': dept_id,
                                'name': f'未映射部门({dept_id[-8:]})',  # 显示部门ID后8位便于识别
                                'status': 'unmapped',
                                'error': '部门未在映射表中，已跳过API调用'
                            }
                            departments.append(unmapped_dept)

                # 缓存用户部门信息
                self._user_departments_cache[cache_key] = {
                    'data': departments,
                    'expire_time': datetime.now() + timedelta(seconds=self._cache_expire_time)  # 设置缓存过期时间
                }

                _safe_print(f"\n📈 部门信息获取完成并已缓存:")
                _safe_print(f"  总部门数: {len(departments)}")
                for dept in departments:
                    _safe_print(f"  - {dept.get('name')} (ID: {dept.get('department_id')})")
                _safe_print("========================\n")

                return departments  # 返回用户的部门信息
            else:
                error_code = result.get('code')
                error_msg = result.get('msg', '未知错误')
                
                _safe_print(f"❌ 飞书API返回错误:")
                _safe_print(f"  错误代码: {error_code}")
                _safe_print(f"  错误信息: {error_msg}")
                
                # 特殊处理 "open_id cross app" 错误
                if error_code == 99992361 or 'cross app' in str(error_msg).lower():
                    _safe_print(f"🔍 检测到 'open_id cross app' 错误，这表示用户的open_id不属于当前应用")
                    _safe_print(f"💡 可能的原因:")
                    _safe_print(f"   1. 用户从不同的飞书应用登录")
                    _safe_print(f"   2. 应用配置不匹配")
                    _safe_print(f"   3. 用户的open_id来自其他应用")
                    _safe_print(f"🔧 建议解决方案:")
                    _safe_print(f"   1. 清除用户session并重新登录")
                    _safe_print(f"   2. 检查飞书应用配置是否正确")
                    _safe_print(f"   3. 确认用户是否在正确的飞书应用中")
                    _safe_print(f"🧹 正在清除相关缓存...")
                    
                    # 清除该用户的缓存
                    self.clear_cache(user_id)
                    
                    _safe_print(f"✅ 缓存已清除，建议用户重新登录")
                
                _safe_print("========================\n")
                return []  # 如果API返回错误，返回空列表

        except Exception as e:
            _safe_print(f"❌ 请求用户信息发生异常:")
            _safe_print(f"  异常类型: {type(e).__name__}")
            _safe_print(f"  异常信息: {str(e)}")
            import traceback
            _safe_print(f"  异常堆栈: {traceback.format_exc()}")
            _safe_print("========================\n")
            return []  # 返回空列表表示获取部门信息失败

    def get_department_info(self, department_id):
        """获取部门详细信息（带缓存）"""
        # 检查缓存
        cache_key = department_id  # 使用部门ID作为缓存的键
        if cache_key in self._department_info_cache:
            cache_data = self._department_info_cache[cache_key]  # 获取缓存数据
            if datetime.now() < cache_data['expire_time']:  # 如果缓存未过期
                _safe_print(f"📋 使用缓存的部门信息: {cache_data['data'].get('name', '未知')}")
                return cache_data['data']  # 返回缓存的部门信息

        token = self.get_access_token()  # 获取应用访问令牌
        if not token:
            return None  # 如果没有令牌，返回 None，表示获取失败

        url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}"  # 获取部门信息的API URL
        headers = {
            "Authorization": f"Bearer {token}",  # 使用获取到的访问令牌进行授权
            "Content-Type": "application/json; charset=utf-8"  # 请求头信息
        }
        params = {
            "department_id_type": "open_department_id"  # 部门ID类型参数，指定为开放部门ID
        }

        try:
            response = self._feishu_request("GET", url, headers=headers, params=params, timeout=10)  # 发送GET请求
            result = response.json()  # 获取响应的JSON数据

            if result.get('code') == 0:  # 如果返回的code是0，表示请求成功
                dept_info = result['data']['department']  # 获取部门的详细信息
                # 缓存部门信息
                self._department_info_cache[cache_key] = {
                    'data': dept_info,
                    'expire_time': datetime.now() + timedelta(seconds=self._cache_expire_time)  # 设置缓存的过期时间
                }
                return dept_info  # 返回部门信息
            else:
                error_code = result.get('code')  # 获取错误代码
                error_msg = result.get('msg', '未知错误')  # 获取错误消息

                # 特殊处理部门不存在的情况
                if error_code == 99992380:  # 飞书API返回的错误码，表示部门ID不存在
                    _safe_print(f"⚠️  部门ID {department_id} 不存在，可能已被删除或重组")
                    # 返回一个默认的部门信息，标记为无效
                    invalid_dept = {
                        'department_id': department_id,
                        'name': '已失效部门',  # 部门名称标记为已失效
                        'status': 'invalid',  # 标记为无效
                        'error': '部门不存在'  # 错误原因
                    }

                    # 缓存失效部门信息（较短时间）
                    self._department_info_cache[cache_key] = {
                        'data': invalid_dept,
                        'expire_time': datetime.now() + timedelta(seconds=60)  # 失效部门缓存1分钟
                    }

                    return invalid_dept  # 返回标记为失效的部门信息
                else:
                    _safe_print(f"❌ 获取部门信息失败: 错误码{error_code}, {error_msg}")
                    return None  # 如果获取部门信息失败，返回 None
        except Exception as e:
            _safe_print(f"❌ 获取部门信息异常: {e}")  # 捕获异常并打印错误信息
            return None  # 返回 None 表示发生异常

    def _get_debug_departments_from_session(self):
        """读取会话里的权限调试部门（仅用于AI部权限联调）"""
        if not has_request_context():
            return []
        request_state = getattr(g, 'permission_debug_state', None)
        raw = (
            request_state.get('departments')
            if isinstance(request_state, dict)
            else session.get('permission_debug_departments')
        )
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        out = []
        seen = set()
        for one in raw:
            name = str(one or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
        return out

    def _get_debug_user_from_session(self):
        """读取会话里的权限调试用户信息（仅用于AI部权限联调）"""
        if not has_request_context():
            return {'name': '', 'open_id': ''}
        request_state = getattr(g, 'permission_debug_state', None)
        if isinstance(request_state, dict):
            return {
                'name': str(request_state.get('user_name') or '').strip(),
                'open_id': str(request_state.get('user_open_id') or '').strip()
            }
        return {
            'name': str(session.get('permission_debug_user_name') or '').strip(),
            'open_id': str(session.get('permission_debug_user_open_id') or '').strip()
        }

    def _ensure_permission_override_storage(self):
        """确保用户级单独授权/禁用表存在。"""
        if self._permission_override_storage_ready:
            return
        with self._permission_override_storage_lock:
            if self._permission_override_storage_ready:
                return
            connection = pytds.connect(**sql_server_config())
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    IF OBJECT_ID(N'dbo.UserPermissionOverrides', N'U') IS NULL
                    BEGIN
                        CREATE TABLE dbo.UserPermissionOverrides (
                            ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                            UserID NVARCHAR(100) NOT NULL,
                            UserName NVARCHAR(200) NULL,
                            FunctionName NVARCHAR(200) NOT NULL,
                            IsAllowed BIT NOT NULL,
                            UpdatedBy NVARCHAR(200) NULL,
                            UpdatedAt DATETIME2 NOT NULL
                                CONSTRAINT DF_UserPermissionOverrides_UpdatedAt DEFAULT GETDATE(),
                            CONSTRAINT UQ_UserPermissionOverrides_User_Function
                                UNIQUE (UserID, FunctionName)
                        )
                    END
                """)
                if not connection.autocommit:
                    connection.commit()
            finally:
                connection.close()
            self._permission_override_storage_ready = True

    def get_user_permission_overrides(self, user_id, force_refresh=False):
        """返回用户级权限覆盖；True=单独授权，False=单独禁用。"""
        normalized_user_id = str(user_id or '').strip()
        if not normalized_user_id:
            return {}
        if not force_refresh:
            cached = self._user_permission_overrides_cache.get(normalized_user_id)
            if cached and datetime.now() < cached['expire_time']:
                return {key: dict(value) for key, value in cached['data'].items()}

        self._ensure_permission_override_storage()
        connection = pytds.connect(**sql_server_config())
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT FunctionName, IsAllowed, UserName, UpdatedBy, UpdatedAt
                FROM dbo.UserPermissionOverrides
                WHERE UserID=%s
                """,
                (normalized_user_id,),
            )
            rows = cursor.fetchall() or []
        finally:
            connection.close()
        overrides = {}
        for row in rows:
            function_name = str(row[0] or '').strip()
            if not function_name:
                continue
            updated_value = row[4] if len(row) > 4 else None
            overrides[function_name] = {
                'is_allowed': bool(row[1]),
                'user_name': str(row[2] or '').strip(),
                'updated_by': str(row[3] or '').strip(),
                'updated_at': updated_value.strftime('%Y-%m-%d %H:%M:%S') if isinstance(updated_value, datetime) else str(updated_value or '').strip(),
            }
        self._user_permission_overrides_cache[normalized_user_id] = {
            'data': {key: dict(value) for key, value in overrides.items()},
            'expire_time': datetime.now() + timedelta(seconds=self._cache_expire_time),
        }
        return overrides

    def set_user_permission_override(self, user_id, function_name, is_allowed, user_name='', updated_by=''):
        normalized_user_id = str(user_id or '').strip()
        normalized_function = str(function_name or '').strip()
        record = self.get_permission_record(normalized_function)
        if not normalized_user_id:
            return {'success': False, 'message': '用户ID不能为空'}
        if not record or normalized_function == '*':
            return {'success': False, 'message': f'功能 {normalized_function} 不存在'}
        self._ensure_permission_override_storage()
        connection = pytds.connect(**sql_server_config())
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                MERGE dbo.UserPermissionOverrides AS target
                USING (SELECT %s AS UserID, %s AS FunctionName) AS source
                ON target.UserID=source.UserID AND target.FunctionName=source.FunctionName
                WHEN MATCHED THEN UPDATE SET
                    UserName=%s, IsAllowed=%s, UpdatedBy=%s, UpdatedAt=GETDATE()
                WHEN NOT MATCHED THEN
                    INSERT (UserID, UserName, FunctionName, IsAllowed, UpdatedBy, UpdatedAt)
                    VALUES (source.UserID, %s, source.FunctionName, %s, %s, GETDATE());
                """,
                (
                    normalized_user_id,
                    normalized_function,
                    str(user_name or '').strip(),
                    bool(is_allowed),
                    str(updated_by or '').strip(),
                    str(user_name or '').strip(),
                    bool(is_allowed),
                    str(updated_by or '').strip(),
                ),
            )
            if not connection.autocommit:
                connection.commit()
        finally:
            connection.close()
        self.clear_cache(normalized_user_id)
        return {
            'success': True,
            'message': '权限已更新',
            'function_display_name': record.get('name') or normalized_function,
            'is_allowed': bool(is_allowed),
        }

    def reset_user_permission_override(self, user_id, function_name):
        normalized_user_id = str(user_id or '').strip()
        normalized_function = str(function_name or '').strip()
        record = self.get_permission_record(normalized_function)
        if not normalized_user_id or not record or normalized_function == '*':
            return {'success': False, 'message': '用户或功能参数无效'}
        self._ensure_permission_override_storage()
        connection = pytds.connect(**sql_server_config())
        try:
            cursor = connection.cursor()
            cursor.execute(
                "DELETE FROM dbo.UserPermissionOverrides WHERE UserID=%s AND FunctionName=%s",
                (normalized_user_id, normalized_function),
            )
            if not connection.autocommit:
                connection.commit()
        finally:
            connection.close()
        self.clear_cache(normalized_user_id)
        return {
            'success': True,
            'message': '已恢复部门默认权限',
            'function_display_name': record.get('name') or normalized_function,
        }

    def get_permission_management_overview(self):
        """返回权限目录、用户级调整及统计概览。"""
        self._ensure_permission_override_storage()
        connection = pytds.connect(**sql_server_config())
        try:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT COUNT(*), COUNT(DISTINCT UserID),
                       SUM(CASE WHEN IsAllowed=1 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN IsAllowed=0 THEN 1 ELSE 0 END)
                FROM dbo.UserPermissionOverrides
            """)
            summary_row = cursor.fetchone() or (0, 0, 0, 0)
            cursor.execute("""
                SELECT TOP 100 UserID, UserName, FunctionName, IsAllowed, UpdatedBy, UpdatedAt
                FROM dbo.UserPermissionOverrides
                ORDER BY UpdatedAt DESC, ID DESC
            """)
            recent_rows = cursor.fetchall() or []
        finally:
            connection.close()
        records = self.get_permission_records()
        summary = {
            'function_count': len([key for key in records if key != '*']),
            'override_count': int(summary_row[0] or 0),
            'user_count': int(summary_row[1] or 0),
            'grant_count': int(summary_row[2] or 0),
            'deny_count': int(summary_row[3] or 0),
        }
        recent = []
        for row in recent_rows:
            function_name = str(row[2] or '').strip()
            updated_value = row[5] if len(row) > 5 else None
            recent.append({
                'user_id': str(row[0] or '').strip(),
                'user_name': str(row[1] or '').strip(),
                'function_name': function_name,
                'function_display_name': (records.get(function_name) or {}).get('name') or function_name,
                'is_allowed': bool(row[3]),
                'updated_by': str(row[4] or '').strip(),
                'updated_at': updated_value.strftime('%Y-%m-%d %H:%M:%S') if isinstance(updated_value, datetime) else str(updated_value or '').strip(),
            })
        catalog = []
        for function_name, record in records.items():
            if function_name == '*':
                continue
            departments = self._split_permission_values(record.get('bumen'))
            catalog.append({
                'function_name': function_name,
                'name': record.get('name') or function_name,
                'description': record.get('description') or '',
                'allowed_departments': ['全员'] if 'all' in departments else departments,
            })
        return {'summary': summary, 'catalog': catalog, 'recent': recent}

    def _get_extra_allowed_functions(self, user_id):
        """按指定用户追加额外权限，不依赖部门配置"""
        if not user_id:
            return []
        try:
            info = self.get_user_info_by_user_id(user_id) or {}
        except Exception:
            info = {}
        user_name = str(info.get('name') or '').strip()
        if not user_name:
            raw_name = str(session.get('feishu_user_name') or '').strip()
            user_name = raw_name.split('（', 1)[0].strip() if raw_name else ''
        extra_functions = list(USER_FUNCTION_OVERRIDES.get(user_name, []))
        if user_name in OPERATION_CARD_OVERRIDE_USERS:
            extra_functions.extend(OPERATION_CARD_OVERRIDE_FUNCTIONS)
        return list(dict.fromkeys(extra_functions))

    def _resolve_effective_departments(self, valid_departments, function_name):
        """
        返回当前权限校验应使用的部门列表。
        - 默认使用真实部门
        - 当会话存在 permission_debug_departments 且用户真实包含 AI部 时，按模拟部门计算
        - 模拟用户的所有功能（包括父级入口和管理员功能）都按模拟身份计算
        """
        real_departments = list(valid_departments or [])
        debug_departments = self._get_debug_departments_from_session()
        debug_user = self._get_debug_user_from_session()
        can_use_debug = 'AI部' in real_departments
        if can_use_debug and (debug_departments or debug_user.get('name')):
            return list(debug_departments), True
        return real_departments, False

    def _resolve_permission_subject_user_id(self, real_user_id, function_name, context):
        """Resolve whose personal grants/denials apply for the current permission row."""
        _, using_debug = self._resolve_effective_departments(
            list((context or {}).get("valid_departments") or []),
            function_name,
        )
        if using_debug:
            debug_open_id = str(
                self._get_debug_user_from_session().get("open_id") or ""
            ).strip()
            if debug_open_id:
                return debug_open_id
        return str(real_user_id or "").strip()

    def _resolve_effective_department_rows(
        self,
        real_user_departments,
        effective_department_names,
        using_debug_departments,
    ):
        """返回权限继承应使用的部门明细，确保模拟用户也按其真实部门树计算。"""
        if not using_debug_departments:
            return list(real_user_departments or [])

        debug_user = self._get_debug_user_from_session()
        debug_open_id = str(debug_user.get('open_id') or '').strip()
        if debug_open_id:
            try:
                debug_rows = self.get_user_departments(debug_open_id) or []
            except Exception as exc:
                _safe_print(f"  ⚠️ 获取权限调试用户部门失败: {exc}")
                debug_rows = []
            if debug_rows:
                return list(debug_rows)

        # 兼容仅选择部门、没有指定模拟用户的旧调试方式。已知部门保留其
        # open_department_id，未知部门仍可参与直接名称匹配，但不会误用登录人的部门树。
        department_ids_by_name = {}
        for department_id, department_name in DEPARTMENT_ID_MAPPING.items():
            normalized_name = str(department_name or '').strip()
            if normalized_name:
                department_ids_by_name.setdefault(normalized_name, []).append(department_id)

        synthetic_rows = []
        for department_name in (effective_department_names or []):
            normalized_name = str(department_name or '').strip()
            if not normalized_name:
                continue
            matched_ids = department_ids_by_name.get(normalized_name) or ['']
            for department_id in matched_ids:
                synthetic_rows.append({
                    'department_id': department_id,
                    'open_department_id': department_id,
                    'name': normalized_name,
                    'status': 'active' if department_id else 'unmapped',
                })
        return synthetic_rows

    def _get_department_root_ids(self, root_name):
        """根据部门名称获取根部门ID集合（支持配置里同名多个ID）。"""
        target = str(root_name or '').strip()
        if not target:
            return set()
        root_ids = set()
        for dept_id, dept_name in DEPARTMENT_ID_MAPPING.items():
            if str(dept_name or '').strip() == target:
                root_ids.add(str(dept_id or '').strip())
        return root_ids

    def _extract_parent_department_ids(self, dept_info):
        """兼容飞书不同字段结构，提取父部门ID列表。"""
        if not isinstance(dept_info, dict):
            return []
        out = []
        parent_id = str(dept_info.get('parent_department_id') or '').strip()
        if parent_id:
            out.append(parent_id)
        parent_ids = dept_info.get('parent_department_ids')
        if isinstance(parent_ids, list):
            for one in parent_ids:
                pid = str(one or '').strip()
                if pid:
                    out.append(pid)
        # 去重但保序
        seen = set()
        unique = []
        for one in out:
            if one in seen:
                continue
            seen.add(one)
            unique.append(one)
        return unique

    def _is_department_under_roots(self, department_id, root_ids, max_depth=16):
        """判断部门是否属于指定根部门树（包含根本身）。"""
        dep_id = str(department_id or '').strip()
        if not dep_id or not root_ids:
            return False
        if dep_id in root_ids:
            return True
        visited = set()
        queue = [dep_id]
        depth = 0
        while queue and depth < max_depth:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            try:
                info = self.get_department_info(current) or {}
            except Exception:
                info = {}
            parent_ids = self._extract_parent_department_ids(info)
            for pid in parent_ids:
                if pid in root_ids:
                    return True
                if pid and pid not in visited:
                    queue.append(pid)
            depth += 1
        return False

    def _department_matches_root_name(self, department_id, root_name, max_depth=16):
        """判断部门是否属于指定根部门树，支持按根名称追溯父级。"""
        dep_id = str(department_id or '').strip()
        target = str(root_name or '').strip()
        if not dep_id or not target:
            return False
        root_ids = self._get_department_root_ids(target)
        if root_ids and self._is_department_under_roots(dep_id, root_ids, max_depth=max_depth):
            return True
        visited = set()
        queue = [dep_id]
        depth = 0
        while queue and depth < max_depth:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            mapped_name = str(DEPARTMENT_ID_MAPPING.get(current) or '').strip()
            if mapped_name == target:
                return True
            try:
                info = self.get_department_info(current) or {}
            except Exception:
                info = {}
            info_name = str(info.get('name') or '').strip()
            if info_name == target:
                return True
            for pid in self._extract_parent_department_ids(info):
                if pid and pid not in visited:
                    queue.append(pid)
            depth += 1
        return False

    def _user_in_department_tree(self, user_departments, root_name):
        """判断用户是否在某个根部门树下（按部门ID追溯父级）。"""
        for row in (user_departments or []):
            if str(row.get('status') or '').strip() == 'invalid':
                continue
            dept_id = str(
                row.get('open_department_id')
                or row.get('department_id')
                or row.get('id')
                or ''
            ).strip()
            if not dept_id:
                continue
            dept_name = str(
                row.get('name') or DEPARTMENT_ID_MAPPING.get(dept_id) or ''
            ).strip()
            if dept_name in DEPARTMENT_TREE_INHERIT_EXCLUDED_DEPARTMENTS:
                continue
            if self._department_matches_root_name(dept_id, root_name):
                return True
        return False

    def _get_tree_inherited_departments(self, user_departments, allowed_departments):
        """返回命中的部门树继承项，例如 内容生产工厂/运营部。"""
        inherited = []
        for root_name in DEPARTMENT_TREE_INHERIT_ROOTS:
            if root_name not in (allowed_departments or []):
                continue
            if self._user_in_department_tree(user_departments, root_name):
                inherited.append(f'{root_name}(子部门继承)')
        return inherited

    @staticmethod
    def _split_permission_values(value):
        """把权限表中的中文分号/英文分号等分隔值标准化为去重列表。"""
        values = []
        seen = set()
        for item in re.split(r"[；;,，、\r\n]+", str(value or "")):
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            values.append(normalized)
        return values

    def _fetch_permission_records_from_db(self):
        """从 dbo.quanxian 读取有效权限；数据库是运行时唯一授权来源。"""
        connection = pytds.connect(**sql_server_config())
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    SELECT ID, GongNeng, YongHu, BuMen, FuJiGongNeng,
                           MingCheng, MiaoShu, QiYong
                    FROM dbo.quanxian
                    WHERE QiYong=1 OR QiYong IS NULL
                    ORDER BY ID
                    """
                )
                raw_rows = cursor.fetchall() or []
            except Exception:
                # 兼容迁移脚本尚未执行的旧四列表结构；授权仍来自表，不回退到代码白名单。
                cursor.execute(
                    "SELECT ID, GongNeng, YongHu, BuMen FROM dbo.quanxian ORDER BY ID"
                )
                raw_rows = [tuple(row) + ("", "", "", 1) for row in (cursor.fetchall() or [])]
        finally:
            connection.close()

        records = {}
        for raw in raw_rows:
            function_name = str(raw[1] or "").strip()
            if not function_name:
                continue
            fallback = PERMISSION_CONFIG.get(function_name, {})
            records[function_name] = {
                "id": raw[0],
                "function_name": function_name,
                "gongneng": function_name,
                "yonghu": str(raw[2] or "").strip(),
                "bumen": str(raw[3] or "").strip(),
                "fujigongneng": str(raw[4] or "").strip(),
                "name": str(raw[5] or fallback.get("name") or function_name).strip(),
                "description": str(raw[6] or fallback.get("description") or "").strip(),
                "enabled": raw[7] is None or bool(raw[7]),
            }
        return records

    def get_permission_records(self, force_refresh=False):
        now = time.time()
        cached = self._permission_rows_cache
        if (
            not force_refresh
            and isinstance(cached, dict)
            and now - self._permission_rows_cached_at < self._permission_rows_cache_ttl
        ):
            return cached
        with self._permission_rows_lock:
            now = time.time()
            cached = self._permission_rows_cache
            if (
                not force_refresh
                and isinstance(cached, dict)
                and now - self._permission_rows_cached_at < self._permission_rows_cache_ttl
            ):
                return cached
            try:
                records = self._fetch_permission_records_from_db()
            except Exception as exc:
                _safe_print(f"❌ 读取 dbo.quanxian 失败: {exc}")
                records = {}
            self._permission_rows_cache = records
            self._permission_rows_cached_at = now
            return records

    def get_permission_record(self, function_name, force_refresh=False):
        return self.get_permission_records(force_refresh=force_refresh).get(
            str(function_name or "").strip()
        )

    def is_permission_enabled(self, function_name):
        return bool(self.get_permission_record(function_name))

    def get_available_permission_departments(self):
        names = set()
        all_tokens = {"all", "*", "全部", "登录用户", "全体已登录用户"}
        for row in self.get_permission_records().values():
            for name in self._split_permission_values(row.get("bumen")):
                if name.lower() not in all_tokens and name not in all_tokens:
                    names.add(name)
        return sorted(names)

    def _permission_user_identities(self, user_id):
        identities = {str(user_id or "").strip()}
        if has_request_context():
            session_user_id = str(session.get("feishu_user_id") or "").strip()
            if not session_user_id or session_user_id == str(user_id or "").strip():
                identities.update(
                    {
                        str(session.get("feishu_user_name") or "").split("（", 1)[0].strip(),
                        str(session.get("feishu_user_email") or "").strip(),
                    }
                )
        if len([value for value in identities if value]) <= 1 and user_id and not str(user_id).startswith("dev_"):
            try:
                info = self.get_user_info_by_user_id(user_id) or {}
            except Exception:
                info = {}
            identities.update(
                {
                    str(info.get("name") or "").split("（", 1)[0].strip(),
                    str(info.get("email") or "").strip(),
                }
            )
        return {value for value in identities if value}

    @staticmethod
    def _department_name_matches(actual_name, allowed_name):
        actual = str(actual_name or "").strip()
        allowed = str(allowed_name or "").strip()
        if not actual or not allowed:
            return False
        if actual == allowed:
            return True
        if allowed in {"运营", "运营部"}:
            return actual.startswith("运营") and actual != "新人组"
        if allowed.endswith("部") and actual == allowed[:-1]:
            return True
        if actual.endswith("部") and actual[:-1] == allowed:
            return True
        return False

    def _permission_context(self, user_id):
        try:
            user_departments = self.get_user_departments(user_id) or []
        except Exception:
            user_departments = []

        # A Feishu contact lookup can briefly return no departments (for example
        # while the tenant token is refreshing).  Do one bounded retry after
        # dropping only this user's department cache; otherwise a transient
        # empty result incorrectly denies every department based permission.
        # Keep this retry local to the permission request and never broaden the
        # database grant itself.
        def _valid_department_names(rows):
            names = []
            for one in rows or []:
                if not isinstance(one, dict):
                    continue
                status = str(one.get("status") or "").strip().lower()
                name = str(one.get("name") or "").strip()
                if status not in {"invalid", "unmapped"} and name:
                    names.append(name)
            return names

        if not _valid_department_names(user_departments) and str(user_id or "").strip():
            try:
                self.clear_cache(str(user_id).strip())
                user_departments = self.get_user_departments(user_id) or []
            except Exception:
                # The first result remains authoritative if the bounded retry
                # also fails; personal permissions are still evaluated below.
                pass

        # Older sessions (and sessions restored after a token expires) may have
        # a department hint captured at login even when the contact API is
        # temporarily unavailable.  Use it only for the real session subject;
        # identity-debug/switch state is still resolved separately below.
        if not _valid_department_names(user_departments) and has_request_context():
            session_user_id = str(session.get("feishu_user_id") or "").strip()
            session_department = str(session.get("user_department") or "").strip()
            if session_department and session_user_id == str(user_id or "").strip():
                user_departments = [{
                    "department_id": f"session:{session_department}",
                    "name": session_department,
                    "status": "active",
                    "source": "session_fallback",
                }]

        valid_names = []
        invalid_names = []
        unmapped_names = []
        for row in user_departments:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").strip().lower()
            name = str(row.get("name") or "").strip()
            if status == "invalid":
                invalid_names.append(name)
            elif status == "unmapped":
                unmapped_names.append(name)
            elif name:
                valid_names.append(name)
        return {
            "user_id": str(user_id or "").strip(),
            # 个人身份可能需要调用飞书用户接口，仅在部门未命中且
            # YongHu 有配置时再延迟获取，保证“部门先判断”。
            "identities": None,
            "user_departments": user_departments,
            "valid_departments": valid_names,
            "invalid_departments": invalid_names,
            "unmapped_departments": unmapped_names,
        }

    def _is_dynamic_department_leader(self, context, effective_department_rows):
        user_id = str(context.get("user_id") or "").strip()
        if not user_id:
            return False
        for row in effective_department_rows or []:
            if not isinstance(row, dict):
                continue
            leader_user_id = str(row.get("leader_user_id") or "").strip()
            if not leader_user_id:
                department_id = str(
                    row.get("department_id") or row.get("open_department_id") or ""
                ).strip()
                if department_id:
                    try:
                        detail = self.get_department_info(department_id) or {}
                    except Exception:
                        detail = {}
                    leader_user_id = str(detail.get("leader_user_id") or "").strip()
            if leader_user_id and leader_user_id == user_id:
                return True
        return False

    def _check_direct_permission_row(self, row, context):
        function_name = str(row.get("function_name") or "").strip()
        real_department_names = list(context.get("valid_departments") or [])
        effective_names, using_debug = self._resolve_effective_departments(
            real_department_names,
            function_name,
        )
        effective_rows = self._resolve_effective_department_rows(
            context.get("user_departments") or [],
            effective_names,
            using_debug,
        )
        permission_subject_context = context
        if using_debug:
            debug_user = self._get_debug_user_from_session()
            debug_open_id = str(debug_user.get("open_id") or "").strip()
            if debug_open_id:
                permission_subject_context = dict(context)
                permission_subject_context["user_id"] = debug_open_id
                permission_subject_context["identities"] = {
                    value for value in {
                        debug_open_id,
                        str(debug_user.get("name") or "").strip(),
                    }
                    if value
                }

        allowed_departments = self._split_permission_values(row.get("bumen"))
        public_tokens = {"all", "*", "全部", "登录用户", "全体已登录用户"}
        if any(value.lower() in public_tokens or value in public_tokens for value in allowed_departments):
            return True, "权限表：全体已登录用户"

        matched_departments = []
        for actual_name in effective_names:
            for allowed_name in allowed_departments:
                if self._department_name_matches(actual_name, allowed_name):
                    matched_departments.append(actual_name)
                    break
        for inherited_name in self._get_tree_inherited_departments(
            effective_rows,
            allowed_departments,
        ):
            if inherited_name not in matched_departments:
                matched_departments.append(inherited_name)
        if matched_departments:
            return True, f"权限表：部门权限通过（{'、'.join(matched_departments)}）"

        allowed_users = set(self._split_permission_values(row.get("yonghu")))
        if "@department_leader" in allowed_users and self._is_dynamic_department_leader(
            permission_subject_context,
            effective_rows,
        ):
            return True, "权限表：部门负责人动态权限"
        identities = permission_subject_context.get("identities")
        if identities is None and allowed_users:
            identities = self._permission_user_identities(
                permission_subject_context.get("user_id")
            )
            permission_subject_context["identities"] = identities
        matched_users = sorted(allowed_users & set(identities or set()))
        if matched_users:
            return True, f"权限表：个人权限通过（{'、'.join(matched_users)}）"
        return False, ""

    def _permission_ancestors(self, function_name, records):
        ancestors = []
        seen = set()
        pending = list(
            self._split_permission_values(
                (records.get(str(function_name or "").strip()) or {}).get("fujigongneng")
            )
        )
        while pending:
            parent = pending.pop(0)
            if not parent or parent in seen:
                continue
            seen.add(parent)
            ancestors.append(parent)
            parent_row = records.get(parent) or {}
            pending.extend(self._split_permission_values(parent_row.get("fujigongneng")))
        return ancestors

    def check_user_permission(self, user_id, function_name):
        """按“部门优先、个人补充、子功能只向上点亮父级”检查权限。"""
        function_name = str(function_name or "").strip()
        records = self.get_permission_records()
        if not records:
            return False, "权限表不可用或无有效权限数据"
        if function_name not in records:
            return False, f"权限表中不存在功能: {function_name}"

        context = self._permission_context(user_id)
        override_cache = {}

        def permission_overrides_for(target_function_name):
            subject_user_id = self._resolve_permission_subject_user_id(
                user_id,
                target_function_name,
                context,
            )
            if subject_user_id in override_cache:
                return override_cache[subject_user_id]
            try:
                overrides = self.get_user_permission_overrides(subject_user_id)
            except Exception as exc:
                _safe_print(f"⚠️ 读取用户单独权限失败，继续使用部门权限: {exc}")
                overrides = {}
            override_cache[subject_user_id] = overrides
            return overrides

        permission_overrides = permission_overrides_for(function_name)
        permission_override = permission_overrides.get(function_name)
        if permission_override is not None:
            if permission_override.get('is_allowed'):
                return True, "用户单独授权"
            return False, "用户单独禁用"

        allowed, reason = self._check_direct_permission_row(records[function_name], context)
        if allowed:
            return True, reason

        wildcard = records.get("*")
        if wildcard:
            allowed, reason = self._check_direct_permission_row(wildcard, context)
            if allowed:
                return True, reason

        # 只有直接拥有子功能才反向点亮父级；父级不会向下放开任何兄弟功能。
        for child_name, child_row in records.items():
            if child_name in {"*", function_name}:
                continue
            if function_name not in self._permission_ancestors(child_name, records):
                continue
            child_override = permission_overrides_for(child_name).get(child_name)
            if child_override is not None:
                if child_override.get('is_allowed'):
                    return True, f"由单独授权的子功能 {child_name} 反向获得父级可见权限"
                continue
            child_allowed, _ = self._check_direct_permission_row(child_row, context)
            if child_allowed:
                return True, f"权限表：由子功能 {child_name} 反向获得父级可见权限"

        department_text = "、".join(context.get("valid_departments") or []) or "无"
        return False, f"无权限访问 {function_name}；当前部门：{department_text}，个人权限未命中"

    def is_developer(self, user_id=None, email=None):
        """开发者也由 quanxian 表中的 `*` 记录识别。"""
        row = self.get_permission_record("*") or {}
        allowed_users = set(self._split_permission_values(row.get("yonghu")))
        candidates = {str(user_id or "").strip(), str(email or "").strip()}
        return bool(allowed_users & {value for value in candidates if value})

    def _legacy_get_user_accessible_functions(self, user_id):
        """获取用户可访问的功能列表（优化版）"""
        _safe_print(f"\n=== 用户权限检查开始 ===")
        _safe_print(f"检查用户: {user_id}")

        accessible_functions = []  # 用于存储用户可以访问的功能

        # 检查是否为开发者模式用户
        if user_id and user_id.startswith('dev_'):
            _safe_print(f"🔧 识别为开发者模式用户: {user_id}")
            # 开发者模式，根据用户类型返回对应权限
            if 'bd' in user_id:
                allowed_functions = ['innovation_proposals', 'tk_project_group',
                                     'script_generator', 'influencer_management']
                _safe_print(f"📋 BD部门权限: {allowed_functions}")
            elif 'video' in user_id:
                allowed_functions = ['innovation_proposals', 'tk_project_group', 'script_generator', 'influencer_management']
                _safe_print(f"📋 短视频部门权限: {allowed_functions}")
            elif 'warehouse' in user_id:
                allowed_functions = ['innovation_proposals', 'warehouse_group']
                _safe_print(f"📋 仓储部门权限: {allowed_functions}")
            elif 'operation1' in user_id:
                allowed_functions = ['innovation_proposals', 'review_analysis', 'operation_dept_1', 'tk_customer_service']
                _safe_print(f"📋 运营一部权限: {allowed_functions}")
            elif 'operation2' in user_id:
                allowed_functions = ['innovation_proposals', 'review_analysis', 'operation_dept_2', 'tk_customer_service']
                _safe_print(f"📋 运营二部权限: {allowed_functions}")
            elif 'operation3' in user_id:
                allowed_functions = ['innovation_proposals', 'review_analysis', 'operation_dept_3', 'tk_customer_service']
                _safe_print(f"📋 运营三部权限: {allowed_functions}")
            elif 'operation6' in user_id:
                allowed_functions = ['innovation_proposals', 'review_analysis', 'operation_dept_6', 'tk_customer_service']
                _safe_print(f"📋 运营六部权限: {allowed_functions}")
            elif 'operation7' in user_id:
                allowed_functions = ['innovation_proposals', 'review_analysis', 'operation_dept_7', 'tk_customer_service']
                _safe_print(f"📋 运营七部权限: {allowed_functions}")
            elif 'ai' in user_id:
                allowed_functions = list(PERMISSION_CONFIG.keys())  # AI部可访问所有功能
                _safe_print(f"📋 AI部门权限: {allowed_functions}")
            elif 'admin' in user_id:
                allowed_functions = list(PERMISSION_CONFIG.keys())  # 总经办可访问所有功能
                _safe_print(f"📋 总经办权限: {allowed_functions}")
            else:
                allowed_functions = ['innovation_proposals']
                _safe_print(f"📋 默认权限: {allowed_functions}")

            # 将开发者模式的权限加入到可访问功能列表
            for func_name in allowed_functions:
                if func_name in PERMISSION_CONFIG:
                    func_config = PERMISSION_CONFIG[func_name]
                    accessible_functions.append({
                        'name': func_config['name'],
                        'function_name': func_name,
                        'description': func_config['description'],
                        'is_developer_access': True
                    })
            _safe_print(f"✅ 开发者模式用户获得权限，共 {len(accessible_functions)} 个功能")
            _safe_print("=========================\n")
            return accessible_functions  # 返回开发者模式用户的权限列表

        # 检查是否为开发者用户
        if self.is_developer(user_id=user_id):
            _safe_print(f"🔧 识别为开发者用户: {user_id}")
            # 开发者可以访问所有功能
            for func_name, func_config in PERMISSION_CONFIG.items():
                accessible_functions.append({
                    'name': func_config['name'],
                    'function_name': func_name,
                    'description': func_config['description'],
                    'is_developer_access': True
                })
            _safe_print(f"✅ 开发者用户获得所有权限，共 {len(accessible_functions)} 个功能")
            _safe_print("=========================\n")
            return accessible_functions  # 返回开发者用户的权限列表

        extra_allowed_functions = self._get_extra_allowed_functions(user_id)
        if extra_allowed_functions:
            _safe_print(f"🎯 指定用户额外权限: {extra_allowed_functions}")

        # 普通用户权限检查 - 优化版：一次性获取用户部门信息
        _safe_print(f"👤 普通用户权限检查开始")
        _safe_print(f"📋 获取用户部门信息...")
        user_departments = self.get_user_departments(user_id)

        # 分离有效部门和无效部门
        valid_departments = []  # 有效部门列表
        invalid_departments = []  # 无效部门列表

        # 遍历用户部门并分类
        for dept in user_departments:
            if dept.get('status') == 'invalid':
                invalid_departments.append(dept.get('name', '未知部门'))  # 无效部门加入无效部门列表
            else:
                valid_departments.append(dept.get('name', ''))  # 有效部门加入有效部门列表

        user_dept_names, using_debug_departments = self._resolve_effective_departments(valid_departments, function_name='__dashboard__')
        effective_user_departments = self._resolve_effective_department_rows(
            user_departments,
            user_dept_names,
            using_debug_departments,
        )
        _safe_print(f"👥 用户有效部门: {valid_departments}")
        if using_debug_departments:
            _safe_print(f"🧪 当前使用权限调试部门: {user_dept_names}")
        if invalid_departments:
            _safe_print(f"⚠️ 用户无效部门: {invalid_departments}")

        # 检查每个功能的权限（使用已获取的部门信息）
        for function_name, config in PERMISSION_CONFIG.items():
            _safe_print(f"\n  检查功能: {config['name']} ({function_name})")

            if function_name in extra_allowed_functions:
                accessible_functions.append({
                    'function_name': function_name,
                    'name': config['name'],
                    'description': config['description'],
                    'reason': '指定用户额外权限'
                })
                _safe_print("  ✅ 权限通过 - 指定用户额外权限")
                continue

            allowed_departments = config['allowed_departments']  # 获取该功能允许访问的部门

            # 如果是全员可见
            if allowed_departments == 'all':
                accessible_functions.append({
                    'function_name': function_name,
                    'name': config['name'],
                    'description': config['description'],
                    'reason': '全员可见'
                })
                _safe_print(f"  ✅ 权限通过 - 全员可见")
                continue

            # 检查部门权限
            authorized_departments = []  # 存储有权限的部门
            for dept_name in user_dept_names:
                if dept_name in allowed_departments:
                    authorized_departments.append(dept_name)  # 如果部门在允许访问的部门列表中，添加到授权部门列表
            for inherited_name in self._get_tree_inherited_departments(effective_user_departments, allowed_departments):
                if inherited_name not in authorized_departments:
                    authorized_departments.append(inherited_name)

            if authorized_departments:
                reason = f"多部门权限通过: {', '.join(authorized_departments)}"  # 如果有授权部门，返回多部门权限通过
                accessible_functions.append({
                    'function_name': function_name,
                    'name': config['name'],
                    'description': config['description'],
                    'reason': reason
                })
                _safe_print(f"  ✅ 权限通过 - {reason}")
            else:
                if invalid_departments:
                    reason = f"无权限访问，当前有效部门: {', '.join(user_dept_names) if user_dept_names else '无'}，无效部门: {', '.join(invalid_departments)}，需要部门: {', '.join(allowed_departments)}"
                else:
                    reason = f"无权限访问，当前部门: {', '.join(user_dept_names) if user_dept_names else '无'}，需要部门: {', '.join(allowed_departments)}"
                _safe_print(f"  ❌ 权限拒绝 - {reason}")

        _safe_print(f"\n✅ 权限检查完成")
        _safe_print(f"📈 用户 {user_id} 可访问功能数量: {len(accessible_functions)}")
        _safe_print(f"📋 可访问功能列表:")
        for func in accessible_functions:
            _safe_print(f"  - {func['name']} ({func.get('reason', 'N/A')})")
        _safe_print("=========================\n")

        return accessible_functions  # 返回用户可访问的功能列表

    def get_user_accessible_functions(self, user_id):
        """返回用户可见功能，仅使用 dbo.quanxian 判定。

        直接命中的子功能会向上补齐父级导航，但不会向下放开兄弟节点。
        """
        records = self.get_permission_records()
        if not records:
            return []

        context = self._permission_context(user_id)
        direct_allowed = set()
        direct_reasons = {}
        override_cache = {}

        def permission_overrides_for(function_name):
            subject_user_id = self._resolve_permission_subject_user_id(
                user_id,
                function_name,
                context,
            )
            if subject_user_id in override_cache:
                return override_cache[subject_user_id]
            try:
                overrides = self.get_user_permission_overrides(subject_user_id)
            except Exception as exc:
                _safe_print(f"⚠️ 读取用户单独权限失败，继续使用权限表规则: {exc}")
                overrides = {}
            override_cache[subject_user_id] = overrides
            return overrides

        wildcard = records.get("*")
        if wildcard:
            allowed, reason = self._check_direct_permission_row(wildcard, context)
            if allowed:
                direct_allowed = set()
                for name in records:
                    if name == "*":
                        continue
                    permission_override = permission_overrides_for(name).get(name)
                    if permission_override is not None and not permission_override.get('is_allowed'):
                        continue
                    direct_allowed.add(name)
                direct_reasons = {name: reason for name in direct_allowed}

        for function_name, row in records.items():
            if function_name == "*":
                continue
            permission_override = permission_overrides_for(function_name).get(function_name)
            if permission_override is not None:
                if permission_override.get('is_allowed'):
                    direct_allowed.add(function_name)
                    direct_reasons[function_name] = '用户单独授权'
                else:
                    direct_allowed.discard(function_name)
                    direct_reasons.pop(function_name, None)
                continue
            if function_name not in direct_allowed:
                allowed, reason = self._check_direct_permission_row(row, context)
                if allowed:
                    direct_allowed.add(function_name)
                    direct_reasons[function_name] = reason

        visible = set(direct_allowed)
        inherited_from = {}
        for child_name in direct_allowed:
            for parent_name in self._permission_ancestors(child_name, records):
                parent_override = permission_overrides_for(parent_name).get(parent_name)
                if parent_name in records and not (
                    parent_override is not None and not parent_override.get('is_allowed')
                ):
                    visible.add(parent_name)
                    inherited_from.setdefault(parent_name, child_name)

        accessible_functions = []
        for function_name, row in records.items():
            if function_name == "*" or function_name not in visible:
                continue
            inherited_child = inherited_from.get(function_name, "")
            reason = direct_reasons.get(function_name)
            if not reason:
                reason = f"由子功能 {inherited_child} 反向获得父级可见权限"
            accessible_functions.append(
                {
                    "function_name": function_name,
                    "name": row.get("name") or function_name,
                    "description": row.get("description") or "",
                    "reason": reason,
                    "is_parent_visibility": function_name not in direct_allowed,
                }
            )
        return accessible_functions

    def search_user_by_id_or_email(self, search_value):
        """根据用户ID、邮箱或飞书姓名搜索用户信息。"""
        try:
            search_value = str(search_value or '').strip()

            # 只有真正像飞书 ID 的输入才请求用户详情接口。旧逻辑会先把中文姓名
            # 当作 ID 请求飞书，必须等待该请求失败后才查询本地姓名映射。
            looks_like_user_id = search_value.startswith(('ou_', 'ou-', 'on_', 'on-', 'u_'))
            if looks_like_user_id:
                user_info = self.get_user_info_by_user_id(search_value)
                if user_info:
                    departments = self.get_user_departments(search_value)
                    return {
                        'user_id': search_value,
                        'name': user_info.get('name', '未知'),
                        'email': user_info.get('email', '未知'),
                        'departments': [dept.get('name', '') for dept in departments]
                    }

            # 如果作为用户ID没找到，尝试作为邮箱搜索
            if '@' in search_value:  # 判断是否为邮箱格式
                user_id = self.search_user_by_email(search_value)
                if user_id:
                    user_info = self.get_user_info_by_user_id(user_id)
                    if user_info:
                        departments = self.get_user_departments(user_id)
                        return {
                            'user_id': user_id,
                            'name': user_info.get('name', '未知'),
                            'email': user_info.get('email', '未知'),
                            'departments': [dept.get('name', '') for dept in departments]
                        }

            # 最后按飞书姓名从本地映射表定位 open_id。
            connection = pytds.connect(**sql_server_config())
            try:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT TOP 1 FeiShu_ID, YONGHU
                    FROM dbo.feishu_id
                    WHERE LTRIM(RTRIM(YONGHU))=%s
                      AND (LEFT(FeiShu_ID, 3)=N'ou_' OR LEFT(FeiShu_ID, 3)=N'ou-')
                    ORDER BY FeiShu_ID
                    """,
                    (str(search_value or '').strip(),),
                )
                matched = cursor.fetchone()
            finally:
                connection.close()
            if matched:
                matched_user_id = str(matched[0] or '').strip()
                matched_name = str(matched[1] or search_value).strip()
                # 本地表已有姓名；部门查询会读取同一个飞书用户，无需再重复请求详情。
                departments = self.get_user_departments(matched_user_id) or []
                return {
                    'user_id': matched_user_id,
                    'name': matched_name or '未知',
                    'email': '未知',
                    'departments': [dept.get('name', '') for dept in departments],
                }

            return None

        except Exception as e:
            _safe_print(f"搜索用户失败: {e}")
            return None

    def search_user_by_email(self, email):
        """通过邮箱搜索用户ID"""
        try:
            # 获取access_token
            access_token = self.get_access_token()
            if not access_token:
                return None

            # 调用飞书API通过邮箱搜索用户
            url = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            data = {
                "emails": [email]
            }

            response = self._feishu_request("POST", url, headers=headers, json=data)

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 0:
                    user_list = result.get('data', {}).get('user_list', [])
                    if user_list:
                        return user_list[0].get('user_id')

            return None

        except Exception as e:
            _safe_print(f"通过邮箱搜索用户失败: {e}")
            return None

    def get_user_info_by_user_id(self, user_id):
        """根据用户ID获取用户基本信息"""
        try:
            # 检查缓存
            import time
            current_time = time.time()

            if user_id in self._user_info_cache:
                cached_data, cache_time = self._user_info_cache[user_id]
                if current_time - cache_time < self._cache_expire_time:
                    return cached_data

            # 获取access_token
            access_token = self.get_access_token()
            if not access_token:
                return None

            # 调用飞书API获取用户信息
            url = f"https://open.feishu.cn/open-apis/contact/v3/users/{user_id}"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            response = self._feishu_request("GET", url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    user_data = data.get('data', {}).get('user', {})
                    user_info = {
                        'name': user_data.get('name', ''),
                        'email': user_data.get('enterprise_email', ''),
                        'mobile': user_data.get('mobile', ''),
                        'avatar': user_data.get('avatar', {})
                    }

                    # 缓存结果
                    self._user_info_cache[user_id] = (user_info, current_time)
                    return user_info

            return None

        except Exception as e:
            _safe_print(f"获取用户信息失败: {e}")
            return None

    def _legacy_get_all_permissions_for_user(self, user_id):
        """获取用户的所有权限信息"""
        try:
            permissions = []

            for function_name, config in PERMISSION_CONFIG.items():
                has_permission, _ = self.check_user_permission(user_id, function_name)

                permissions.append({
                    'function_name': function_name,
                    'name': config['name'],
                    'description': config['description'],
                    'has_permission': has_permission
                })

            return permissions

        except Exception as e:
            _safe_print(f"获取用户权限信息失败: {e}")
            return []

    def _legacy_grant_user_permission(self, user_id, function_name):
        """授予用户权限"""
        try:
            # 检查功能是否存在
            if function_name not in PERMISSION_CONFIG:
                return {
                    'success': False,
                    'message': f'功能 {function_name} 不存在'
                }

            # 获取功能配置
            config = PERMISSION_CONFIG[function_name]

            # 检查用户是否已有权限
            has_permission, _ = self.check_user_permission(user_id, function_name)
            if has_permission:
                return {
                    'success': False,
                    'message': f'用户已拥有 {config["name"]} 权限'
                }

            # 这里需要实现权限授予逻辑
            # 由于当前系统基于部门权限，我们需要创建一个用户特定权限的存储机制
            # 暂时返回成功，实际应用中需要将权限信息存储到数据库

            # 清除用户相关缓存
            self.clear_cache(user_id)

            return {
                'success': True,
                'message': f'成功授予 {config["name"]} 权限',
                'function_display_name': config['name']
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'授予权限失败: {str(e)}'
            }

    def _legacy_revoke_user_permission(self, user_id, function_name):
        """撤销用户权限"""
        try:
            # 检查功能是否存在
            if function_name not in PERMISSION_CONFIG:
                return {
                    'success': False,
                    'message': f'功能 {function_name} 不存在'
                }

            # 获取功能配置
            config = PERMISSION_CONFIG[function_name]

            # 检查用户是否有权限
            has_permission, _ = self.check_user_permission(user_id, function_name)
            if not has_permission:
                return {
                    'success': False,
                    'message': f'用户没有 {config["name"]} 权限'
                }

            # 这里需要实现权限撤销逻辑
            # 由于当前系统基于部门权限，我们需要创建一个用户特定权限的存储机制
            # 暂时返回成功，实际应用中需要从数据库中移除权限信息

            # 清除用户相关缓存
            self.clear_cache(user_id)

            return {
                'success': True,
                'message': f'成功撤销 {config["name"]} 权限',
                'function_display_name': config['name']
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'撤销权限失败: {str(e)}'
            }

    def get_all_permissions_for_user(self, user_id):
        """返回权限表中的全部功能及该用户的实时授权状态。"""
        try:
            overrides = self.get_user_permission_overrides(user_id)
        except Exception:
            overrides = {}
        permissions = []
        for function_name, row in self.get_permission_records().items():
            if function_name == "*":
                continue
            has_permission, reason = self.check_user_permission(user_id, function_name)
            override = overrides.get(function_name)
            permissions.append(
                {
                    "function_name": function_name,
                    "name": row.get("name") or function_name,
                    "description": row.get("description") or "",
                    "has_permission": has_permission,
                    "reason": reason,
                    "override_state": (
                        'allow' if override and override.get('is_allowed')
                        else ('deny' if override is not None else None)
                    ),
                }
            )
        return permissions

    def _target_permission_identities(self, user_id):
        identities = {str(user_id or "").strip()}
        try:
            info = self.get_user_info_by_user_id(user_id) or {}
        except Exception:
            info = {}
        identities.update(
            {
                str(info.get("name") or "").split("（", 1)[0].strip(),
                str(info.get("email") or "").strip(),
            }
        )
        return {value for value in identities if value}, info

    def _update_permission_users(self, function_name, users):
        normalized_users = []
        seen = set()
        for user in users:
            value = str(user or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized_users.append(value)
        connection = pytds.connect(**sql_server_config())
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.quanxian
                SET YongHu=%s, GengXinShiJian=SYSDATETIME()
                WHERE LTRIM(RTRIM(GongNeng))=%s
                """,
                ("；".join(normalized_users), str(function_name or "").strip()),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"权限表中不存在功能: {function_name}")
            if not connection.autocommit:
                connection.commit()
        finally:
            connection.close()
        self.clear_cache()

    def grant_user_permission(self, user_id, function_name, user_name='', updated_by=''):
        """写入用户级单独授权，优先于部门默认规则。"""
        try:
            return self.set_user_permission_override(
                user_id,
                function_name,
                True,
                user_name=user_name,
                updated_by=updated_by,
            )
        except Exception as exc:
            return {'success': False, 'message': f'授予权限失败: {exc}'}

    def revoke_user_permission(self, user_id, function_name, user_name='', updated_by=''):
        """写入用户级单独禁用，优先于部门默认规则。"""
        try:
            return self.set_user_permission_override(
                user_id,
                function_name,
                False,
                user_name=user_name,
                updated_by=updated_by,
            )
        except Exception as exc:
            return {'success': False, 'message': f'撤销权限失败: {exc}'}


# 全局权限管理器实例
permission_manager = FeishuPermissionManager()


def require_permission(function_name):
    """权限装饰器"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 导入request对象
            from flask import request

            # 从session获取用户信息
            user_id = session.get('feishu_user_id')

            if not user_id:
                # 检查是否为本地开发环境
                is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')

                if is_local_dev:
                    # 本地开发环境，跳转到开发者登录
                    return redirect(url_for('dev_login', user_type='bd'))
                else:
                    # API请求返回JSON，避免302跳转被前端当成接口失败
                    if request.path.startswith('/api/') or request.headers.get('Content-Type') == 'application/json':
                        return jsonify({
                            'success': False,
                            'error': '未登录',
                            'message': '未检测到飞书登录状态，请重新登录',
                            'auth_url': url_for('feishu_auth')
                        }), 401
                    # 非API请求重定向到飞书授权
                    return redirect(url_for('feishu_auth'))

            # 检查权限
            try:
                has_permission, reason = permission_manager.check_user_permission(user_id, function_name)
            except Exception as e:
                if request.path.startswith('/api/') or request.headers.get('Content-Type') == 'application/json':
                    return jsonify({
                        'success': False,
                        'error': '权限检查异常',
                        'message': f'权限校验失败: {str(e)}',
                        'required_function': function_name
                    }), 500
                return redirect(url_for('feishu_auth'))

            if not has_permission:
                # 检查请求类型，如果是API请求返回JSON，否则重定向到dashboard
                if request.path.startswith('/api/') or request.headers.get('Content-Type') == 'application/json':
                    return jsonify({
                        'error': '权限不足',
                        'message': reason,
                        'required_function': function_name
                    }), 403
                else:
                    # 对于页面请求，重定向到dashboard并显示错误信息
                    from flask import flash
                    flash(f'权限不足：{reason}', 'error')
                    return redirect(url_for('dashboard'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_feishu_auth_url():
    """生成飞书授权URL"""
    # 新版用户授权入口（End User Consent）
    base_url = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"

    # 检查是否在飞书环境中运行
    host = request.headers.get('Host', '') if request else ''

    # 强制使用内网穿透地址，因为飞书无法访问localhost
    redirect_uri = FEISHU_CONFIG['production_domain'] + FEISHU_CONFIG['callback_path']

    # 仅申请当前实现真正需要的用户身份权限，避免跳转授权页提示不存在的 history scope
    scopes = [
        "contact:user.id:readonly",
        "im:chat",
        "im:chat:read",
        "im:chat:readonly",
        "im:message:readonly",
        "im:message",
        "im:message.group_msg:get_as_user",
        "im:message.p2p_msg:get_as_user",
    ]
    force_reauth = str(request.args.get('force') or session.get('force_feishu_reauth') or '').strip().lower() in {'1', 'true', 'yes'}
    state = "tuchuang_ai_system"
    if force_reauth:
        state = f"tuchuang_ai_system:reauth:{int(datetime.now().timestamp())}"
    params = {
        "client_id": FEISHU_CONFIG['app_id'],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state
    }
    if force_reauth:
        params["prompt"] = "consent"

    # 使用urllib.parse.urlencode来正确编码参数
    import urllib.parse
    param_string = urllib.parse.urlencode(params)
    auth_url = f"{base_url}?{param_string}"

    return auth_url


def handle_feishu_event(data):
    """处理飞书事件回调"""
    from flask import jsonify

    try:
        event = data.get('event', {})  # 获取事件数据（如果没有则返回空字典）
        event_type = event.get('type')  # 获取事件类型

        _safe_print(f"处理飞书事件: {event_type}")  # 打印事件类型
        _safe_print(f"事件数据: {event}")  # 打印完整的事件数据

        # 这里可以根据不同的事件类型进行处理
        # 例如：用户加入、离开、消息等

        return jsonify({"msg": "ok"}), 200  # 返回成功响应，表示事件处理成功

    except Exception as e:
        _safe_print(f"处理飞书事件失败: {e}")  # 如果发生异常，打印错误信息
        return jsonify({"error": "处理事件失败"}), 500  # 返回失败响应

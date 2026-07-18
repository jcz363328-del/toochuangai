import requests
import json
from functools import wraps
from flask import request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import os
import hashlib
import hmac
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import binascii

from secret_settings import FEISHU_CONFIG as SECRET_FEISHU_CONFIG
from tools import safe_print as _safe_print


# 飞书应用配置
FEISHU_CONFIG = dict(SECRET_FEISHU_CONFIG)

# 部门ID映射配置 - 硬编码部门ID和名称的对应关系，避免频繁API调用
DEPARTMENT_ID_MAPPING = {
    # 根据实际飞书组织架构配置部门ID和名称的映射关系
    # 格式: 'department_id': 'department_name'
    'od-c560effca33bf715c15f79a0670fe6ba': '内容生产工厂',
    'od-1fd573a06618d5efc50558aa4c6c8fde': 'BD部',
    'od-411009520c49cf4d96112d486356cacd': '短视频部',
    'od-3a5fdfc4a7c8a87f5f35b297dce74113': '客服',
    'od-996da0561bdfe1bfb6ddb42adaa3b0e3': '产品&店铺运营',
    'od-44dc61c250f0246d8d91bb606828cc15': '总经办',
    'od-b07e2f864d107ce0a4b85b2b41fa4789': '运营一部',
    'od-116119842dc8080c84f3136f53732d94': '运营二部',
    'od-6fe88bb79ed3fce51ed344dfe7f57297': '运营三部',
    'od-32e208044431366fa2d61f78176d88c8': '运营六部',
    'od-9929dd4f4d3b0be7c1f635d17e46ae22': '采购部',
    'od-364835a9f7cc1ad050046cd995f886e4': '研发部',
    'od-bca4e38e980226d367f7c501b3697e5a': '技术部',
    'od-791aa15d697bd40782942379363d4f21': '视觉设计部',
    'od-533088d36a43c281e0a2e99161e7e6a9': '摄影部',
    'od-f652a036dd421ff38d25b92e423026df': 'AI部',
    'od-e7b5654df37bd9375225e8fce462a408': '财务部',
    'od-f400f2b1de53f7303b589420f14b6c5a': '人力行政部',
    'od-580f76720379d11ad66be30aaf7034a4': '新人组',
    'od-692236b3673407d6c0333c42fd6b01af': '仓储部',
    'od-6fffe97f7129ad9bc85162ac5cabcb20': 'TK部门',
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
        'allowed_departments': ['运营部', 'AI部', '总经办'],  # 运营部及其下各运营分部 + AI部和总经办
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
]

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
        self._direct_http = requests.Session()
        self._direct_http.trust_env = False

    def _feishu_request(self, method, url, **kwargs):
        try:
            return requests.request(method=method, url=url, **kwargs)
        except requests.exceptions.ProxyError as e:
            _safe_print(f"⚠️ 代理连接失败，切换直连重试: {e}")
            return self._direct_http.request(method=method, url=url, **kwargs)

    def clear_cache(self, user_id=None):
        """清理缓存"""
        if user_id:
            # 如果传入 user_id，则只清理该用户的缓存
            if user_id in self._user_departments_cache:
                del self._user_departments_cache[user_id]  # 删除该用户的部门缓存
                _safe_print(f"🧹 已清理用户 {user_id} 的部门缓存")
        else:
            # 如果没有传入 user_id，则清理所有缓存（全局清空）
            self._user_departments_cache.clear()
            self._department_info_cache.clear()
            self._user_info_cache.clear()
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
        _safe_print(f"🔑 授权码: {code}")  # 打印授权码

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
        _safe_print(f"📦 请求数据: {data}")  # 打印请求的数据

        try:
            _safe_print(f"🚀 发送请求获取用户访问令牌...")
            response = self._feishu_request("POST", url, headers=headers, json=data, timeout=10)  # 发送请求
            _safe_print(f"📊 响应状态码: {response.status_code}")  # 打印响应的状态码
            _safe_print(f"📄 响应头: {dict(response.headers)}")  # 打印响应头
            result = response.json()  # 获取响应结果
            _safe_print(f"📋 响应内容: {result}")  # 打印响应内容

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
                _safe_print(f"✅ 用户访问令牌获取成功: {user_access_token[:20]}...")  # 打印用户 token（部分）
                _safe_print(f"🔄 开始通过用户令牌获取用户信息...")
                user_info = self.get_user_info_by_token(user_access_token)  # 使用用户 token 获取用户信息
                if isinstance(user_info, dict):
                    user_info['user_access_token'] = user_access_token
                    user_info['user_refresh_token'] = token_data.get('refresh_token', '')
                    user_info['user_token_expires_in'] = token_data.get('expires_in', 0)
                    user_info['user_refresh_expires_in'] = token_data.get('refresh_expires_in', 0)
                _safe_print(f"📋 最终用户信息: {user_info}")  # 打印最终的用户信息
                _safe_print("========================\n")
                return user_info  # 返回用户信息
            else:
                _safe_print(f"❌ 通过code获取用户token失败")  # 如果失败，打印失败信息
                _safe_print(f"🔍 错误代码: {result.get('code')}")  # 打印错误代码
                _safe_print(f"🔍 错误消息: {result.get('msg')}")  # 打印错误消息
                _safe_print(f"🔍 完整响应: {result}")  # 打印完整的响应信息
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
        _safe_print(f"✅ 访问令牌获取成功: {token[:20]}...")  # 打印访问令牌（部分）

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
        _safe_print(f"  Headers: {headers}")
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
        raw = session.get('permission_debug_departments')
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
        return {
            'name': str(session.get('permission_debug_user_name') or '').strip(),
            'open_id': str(session.get('permission_debug_user_open_id') or '').strip()
        }

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
        if user_name in OPERATION_CARD_OVERRIDE_USERS:
            return list(OPERATION_CARD_OVERRIDE_FUNCTIONS)
        return []

    def _resolve_effective_departments(self, valid_departments, function_name):
        """
        返回当前权限校验应使用的部门列表。
        - 默认使用真实部门
        - 当会话存在 permission_debug_departments 且用户真实包含 AI部 时，按模拟部门计算
        - 为避免调试入口被锁死，ai_dept/admin_functions 始终按真实部门
        """
        real_departments = list(valid_departments or [])
        debug_departments = self._get_debug_departments_from_session()
        debug_user = self._get_debug_user_from_session()
        bypass_debug_functions = {'ai_dept', 'admin_functions'}
        can_use_debug = ('AI部' in real_departments) and function_name not in bypass_debug_functions
        if can_use_debug and (debug_departments or debug_user.get('name')):
            return list(debug_departments), True
        return real_departments, False

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

    def check_user_permission(self, user_id, function_name):
        """检查用户是否有访问指定功能的权限

        多部门权限策略：
        - 如果用户属于多个部门，权限取并集
        - 只要有一个部门有权限，用户就有权限
        """
        # 检查是否为开发者
        if self.is_developer(user_id):
            return True, "开发者权限"  # 如果是开发者，直接返回开发者权限

        # 获取功能权限配置
        if function_name not in PERMISSION_CONFIG:
            return False, "功能不存在"  # 如果功能不存在，返回失败

        extra_allowed_functions = self._get_extra_allowed_functions(user_id)
        if function_name in extra_allowed_functions:
            return True, "指定用户额外权限"

        permission_config = PERMISSION_CONFIG[function_name]  # 获取功能的权限配置
        allowed_departments = permission_config['allowed_departments']  # 获取允许访问该功能的部门

        # 如果是全员可见
        if allowed_departments == 'all':
            return True, "全员可见"  # 如果功能对所有人开放，返回权限通过

        # 获取用户部门信息
        user_departments = self.get_user_departments(user_id)  # 获取用户所属部门信息

        # 分离有效部门、无效部门和未映射部门
        valid_departments = []  # 有效部门列表
        invalid_departments = []  # 无效部门列表
        unmapped_departments = []  # 未映射部门列表

        for dept in user_departments:  # 遍历用户的部门
            dept_status = dept.get('status')  # 获取部门状态
            dept_name = dept.get('name', '未知部门')  # 获取部门名称

            if dept_status == 'invalid':
                invalid_departments.append(dept_name)  # 如果部门无效，加入无效部门列表
            elif dept_status == 'unmapped':
                unmapped_departments.append(dept_name)  # 如果部门未映射，加入未映射部门列表
            else:
                valid_departments.append(dept_name)  # 否则，加入有效部门列表

        user_dept_names, using_debug_departments = self._resolve_effective_departments(valid_departments, function_name)
        effective_user_departments = self._resolve_effective_department_rows(
            user_departments,
            user_dept_names,
            using_debug_departments,
        )

        _safe_print(f"\n🔍 多部门权限检查:")  # 打印权限检查的调试信息
        _safe_print(f"  用户ID: {user_id}")
        _safe_print(f"  功能: {function_name}")
        _safe_print(f"  用户有效部门: {valid_departments}")
        if using_debug_departments:
            _safe_print(f"  权限调试部门(会话模拟): {user_dept_names}")
        if invalid_departments:
            _safe_print(f"  用户无效部门: {invalid_departments} (已失效，不参与权限计算)")
        if unmapped_departments:
            _safe_print(f"  用户未映射部门: {unmapped_departments} (未在映射表中，不参与权限计算)")
        _safe_print(f"  功能允许部门: {allowed_departments}")

        # 多部门权限取并集：检查用户的每个有效部门是否在允许列表中
        authorized_departments = []  # 存储有权限的部门
        for dept_name in user_dept_names:
            if dept_name in allowed_departments:  # 如果用户的部门在允许访问的部门列表中
                authorized_departments.append(dept_name)  # 将该部门添加到授权部门列表
        for inherited_name in self._get_tree_inherited_departments(effective_user_departments, allowed_departments):
            if inherited_name not in authorized_departments:
                authorized_departments.append(inherited_name)

        if authorized_departments:
            result_msg = f"多部门权限通过: {', '.join(authorized_departments)}"  # 权限通过，返回通过的部门列表
            _safe_print(f"  ✅ 权限结果: {result_msg}")
            return True, result_msg  # 返回 True，表示权限通过
        else:
            # 构建详细的权限拒绝消息
            msg_parts = []  # 用于存储拒绝信息
            base_label = "当前模拟部门" if using_debug_departments else "当前有效部门"
            msg_parts.append(f"{base_label}: {', '.join(user_dept_names) if user_dept_names else '无'}")

            if invalid_departments:
                msg_parts.append(f"无效部门: {', '.join(invalid_departments)}")  # 如果有无效部门，显示
            if unmapped_departments:
                msg_parts.append(f"未映射部门: {', '.join(unmapped_departments)}")  # 如果有未映射部门，显示
            msg_parts.append(f"需要部门: {', '.join(allowed_departments)}")  # 显示该功能需要的部门

            result_msg = f"无权限访问，{', '.join(msg_parts)}"  # 组合权限拒绝信息
            _safe_print(f"  ❌ 权限结果: {result_msg}")
            return False, result_msg  # 返回 False，表示权限不通过

    def is_developer(self, user_id=None, email=None):
        """检查是否为开发者"""
        # 如果开发者模式未启用，则直接返回 False
        if not DEVELOPER_CONFIG['enabled']:
            return False

        # 如果传入了 user_id 且该用户在开发者ID列表中，则返回 True
        if user_id and user_id in DEVELOPER_CONFIG['developer_user_ids']:
            return True

        # 如果传入了 email 且该邮箱在开发者邮箱列表中，则返回 True
        if email and email in DEVELOPER_CONFIG['developer_emails']:
            return True

        # 如果没有找到，返回 False
        return False

    def get_user_accessible_functions(self, user_id):
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

    def search_user_by_id_or_email(self, search_value):
        """根据用户ID或邮箱搜索用户信息"""
        try:
            # 首先尝试作为用户ID搜索
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

    def get_all_permissions_for_user(self, user_id):
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

    def grant_user_permission(self, user_id, function_name):
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

    def revoke_user_permission(self, user_id, function_name):
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

            # 开发者模式用户权限检查
            if user_id.startswith('dev_'):
                # 根据开发者用户类型检查权限
                if 'bd' in user_id and function_name in ['review_analysis', 'innovation_proposals', 'script_generator',
                                                         'influencer_management']:
                    return f(*args, **kwargs)
                elif 'video' in user_id and function_name in ['review_analysis', 'innovation_proposals',
                                                              'script_generator']:
                    return f(*args, **kwargs)
                elif 'ai' in user_id and function_name in ['review_analysis', 'innovation_proposals',
                                                           'admin_functions']:
                    return f(*args, **kwargs)
                elif 'admin' in user_id:  # 总经办可访问所有功能
                    return f(*args, **kwargs)
                else:
                    # 检查请求类型，如果是API请求返回JSON，否则重定向到dashboard
                    if request.path.startswith('/api/') or request.headers.get('Content-Type') == 'application/json':
                        return jsonify({
                            'error': '权限不足',
                            'message': f'开发者模式用户无权访问 {function_name} 功能',
                            'required_function': function_name
                        }), 403
                    else:
                        # 对于页面请求，重定向到dashboard并显示错误信息
                        from flask import flash
                        flash(f'权限不足：开发者模式用户无权访问 {function_name} 功能', 'error')
                        return redirect(url_for('dashboard'))

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

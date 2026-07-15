# -*- coding: utf-8 -*-
"""
统一消息发送服务模块
基于bjc.py的send_message函数实现，用于替换现有的FeishuBot
"""

import os
import sys
import requests
import json
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from bjc import sf_db, dui_db
from secret_settings import get_feishu_message_config, relocate_storage_path

try:
    from .config import DEPARTMENT_FEISHU_MAPPING, DEFAULT_NOTIFICATION_RECEIVER
except Exception:
    try:
        from config import DEPARTMENT_FEISHU_MAPPING, DEFAULT_NOTIFICATION_RECEIVER
    except Exception:
        DEPARTMENT_FEISHU_MAPPING = {}
        DEFAULT_NOTIFICATION_RECEIVER = ""


class MessageService:
    """统一消息发送服务类"""

    def __init__(self, company_key='company1'):
        """初始化消息服务

        Args:
            company_key: 公司配置键名，默认为'company1'
        """
        self.company_key = company_key
        feishu_config = get_feishu_message_config()
        self.app_id = feishu_config["app_id"]
        self.app_secret = feishu_config["app_secret"]
        self._access_token = None
        self._access_token_expire_at = None

    def _get_access_token(self):
        if self._access_token and self._access_token_expire_at and datetime.now() < self._access_token_expire_at:
            return self._access_token
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret}
        )
        data = r.json() or {}
        token = data.get("tenant_access_token")
        expire = data.get("expire") or 0
        if token:
            expire_seconds = int(expire) if str(expire).isdigit() else 0
            if expire_seconds > 0:
                self._access_token_expire_at = datetime.now() + timedelta(seconds=max(0, expire_seconds - 60))
            else:
                self._access_token_expire_at = datetime.now() + timedelta(minutes=30)
            self._access_token = token
        return token

    def esc(self, v):
        """转义SQL字符串"""
        return '' if v is None else str(v).replace("'", "''")

    def _normalize_id_list(self, raw_value):
        if not raw_value:
            return []
        values = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
        out = []
        seen = set()
        for item in values:
            if isinstance(item, dict):
                candidates = [
                    item.get("FeiShu_ID"),
                    item.get("feishu_id"),
                    item.get("open_id"),
                    item.get("user_id"),
                    item.get("id"),
                ]
            elif isinstance(item, (list, tuple)):
                candidates = list(item)
            else:
                candidates = [item]
            for candidate in candidates:
                fid = str(candidate or "").strip()
                if not fid or fid in seen:
                    continue
                seen.add(fid)
                out.append(fid)
        return out

    def _is_department_id(self, value):
        value = str(value or "").strip()
        return value.startswith("od_") or value.startswith("od-")

    def _is_personal_receive_id(self, value):
        value = str(value or "").strip()
        return value.startswith("ou_") or "@" in value

    def _resolve_mapping_targets(self, department_name):
        raw_targets = DEPARTMENT_FEISHU_MAPPING.get(str(department_name or "").strip())
        resolved = []
        for target in self._normalize_id_list(raw_targets):
            if self._is_personal_receive_id(target):
                resolved.append(target)
                continue
            try:
                rows = sf_db(
                    f"SELECT TOP 1 FeiShu_ID FROM feishu_id WHERE FeiShu_ID='{self.esc(target)}' OR YONGHU='{self.esc(target)}' "
                    "ORDER BY CASE WHEN FeiShu_ID LIKE 'ou[_]%%' THEN 0 ELSE 1 END"
                )
                resolved.extend([fid for fid in self._normalize_id_list(rows) if self._is_personal_receive_id(fid)])
            except Exception as e:
                print(f"查询部门兜底接收人失败 {target}: {e}")
        if not resolved and DEFAULT_NOTIFICATION_RECEIVER:
            resolved.extend([fid for fid in self._normalize_id_list(DEFAULT_NOTIFICATION_RECEIVER) if self._is_personal_receive_id(fid)])
        deduped = []
        seen = set()
        for fid in resolved:
            if fid not in seen:
                seen.add(fid)
                deduped.append(fid)
        return deduped

    def detect_type(self, fid):
        """检测飞书ID类型"""
        if fid.startswith("oc_"): return "chat_id"
        if fid.startswith("ou_"): return "open_id"
        # od_ 是部门ID，不能作为IM消息接收人；部门消息应先展开到个人ou_再发送
        if fid.startswith("od_") or fid.startswith("od-"): return "open_department_id"
        if "@" in fid: return "email"
        return "user_id"

    def send_message(self, chat_name, message, image_path=None, at_users=None, at_all=False, image_paths=None):
        """
        发送图文混合消息到飞书（个人或群组）
        基于bjc.py的send_message函数实现

        Args:
            chat_name: 表 feishu_id.YONGHU（查库找 FeiShu_ID）或直接传 FeiShu_ID (oc_/ou_/od_/ou_) 或邮箱
            message: 消息文本
            image_path: 单张图片路径（兼容旧接口）
            at_users: @的人名字列表（从feishu_id表查 FeiShu_ID，必须是 ou_xxx）
            at_all: True 表示 @所有人
            image_paths: 图片路径列表（可以多张），默认 None

        Returns:
            bool: 发送成功返回True，失败返回False
        """
        if not (chat_name and message):
            print("❌ 参数缺失")
            return False

        # 兼容处理：如果传入了image_path但没有image_paths，则转换
        if image_path and not image_paths:
            image_paths = [image_path]

        # 获取 FeiShu_ID
        if chat_name.startswith(("oc_", "ou_", "od_")) or "@" in chat_name:
            fid = chat_name
        else:
            rows = sf_db(f"SELECT FeiShu_ID FROM feishu_id WHERE YONGHU='{self.esc(chat_name)}'")
            if not rows:
                print(f"❌ 未找到 {chat_name} 的 FeiShu_ID，请确认 feishu_id 表有记录")
                return False
            fid = rows if isinstance(rows, str) else rows[0]

        access_token = self._get_access_token()
        if not access_token:
            print("❌ 获取 token 失败")
            return False

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=utf-8"}
        msg_url = "https://open.feishu.cn/open-apis/im/v1/messages"
        img_url = "https://open.feishu.cn/open-apis/im/v1/images"

        # 构建文本 / @消息
        if at_users or at_all:
            # 查 open_id
            elements = [{"tag": "text", "text": message + " "}]

            if at_users:
                for uname in at_users:
                    row2 = sf_db(f"SELECT FeiShu_ID FROM feishu_id WHERE YONGHU='{self.esc(uname)}'")
                    if row2:
                        uid = row2 if isinstance(row2, str) else row2[0]
                        if uid.startswith("ou_"):
                            elements.append({"tag": "at", "user_id": uid})
                            elements.append({"tag": "text", "text": " "})

            if at_all:
                elements.append({"tag": "at", "user_id": "all"})
                elements.append({"tag": "text", "text": " "})

            payload = {
                "receive_id": fid,
                "msg_type": "post",
                "content": json.dumps({
                    "zh_cn": {
                        "content": [elements]
                    }
                }, ensure_ascii=False)
            }
        else:
            payload = {"receive_id": fid, "msg_type": "text",
                       "content": json.dumps({"text": message}, ensure_ascii=False)}

        # 发送文字 / @消息
        rid_type = self.detect_type(fid)
        if rid_type == "open_department_id":
            print(f"❌ 不支持直接向部门ID发送IM消息: {fid}")
            return False
        r = requests.post(
            f"{msg_url}?receive_id_type={rid_type}",
            headers=headers, json=payload
        ).json()
        print("➡️ 文本/AT 发送结果:", r)
        success = r.get("code") == 0

        # 发送图片（多张）
        if image_paths:
            for img in image_paths:
                img = relocate_storage_path(img)
                if not os.path.exists(img):
                    print(f"⚠️ 图片不存在: {img}")
                    continue
                with open(img, "rb") as f:
                    files = {"image": (os.path.basename(img), f, "image/png")}
                    data = {"image_type": "message"}
                    resp = requests.post(img_url, headers={"Authorization": f"Bearer {access_token}"}, files=files,
                                         data=data).json()
                    image_key = resp.get("data", {}).get("image_key")
                    if image_key:
                        img_payload = {"receive_id": fid, "msg_type": "image",
                                       "content": json.dumps({"image_key": image_key})}
                        r2 = requests.post(
                            f"{msg_url}?receive_id_type={rid_type}",
                            headers=headers, json=img_payload
                        ).json()
                        print(f"➡️ 图片 {img} 发送结果:", r2)
                        success = success and (r2.get("code") == 0)

        # 记录日志
        if success:
            sql = (f"INSERT INTO FaYouJian VALUES('飞书消息推送','{self.esc(chat_name)}->{fid}',"
                   f"'飞书消息','{self.esc(message)}',GETDATE(),'123456789',GETDATE())")
            try:
                dui_db(sql, show_result=True)
            except Exception as e:
                print(f"记录消息日志异常: {e}")

        return success

    def send_message_to_department_members(self, department_name, message_content, at_all=False):
        """向部门所有成员发送消息

        Args:
            department_name: 部门名称
            message_content: 消息内容
            at_all: 是否@所有人

        Returns:
            dict: 发送结果统计
        """
        try:
            # 获取部门下所有个人用户ID
            personal_members = self.get_department_contacts(department_name)

            if not personal_members:
                print(f"未找到部门 '{department_name}' 的成员")
                return {'success': 0, 'failed': 0, 'total': 0}

            print(f"准备向部门 '{department_name}' 的 {len(personal_members)} 个成员发送消息")

            success_count = 0
            failed_count = 0

            # 逐个发送消息给每个成员
            for member_id in personal_members:
                try:
                    result = self.send_message(member_id, message_content, at_all=at_all)
                    if result:
                        success_count += 1
                        print(f"✅ 成功发送给 {member_id}")
                    else:
                        failed_count += 1
                        print(f"❌ 发送失败给 {member_id}")
                except Exception as e:
                    failed_count += 1
                    print(f"❌ 发送异常给 {member_id}: {e}")

            result_summary = {
                'success': success_count,
                'failed': failed_count,
                'total': len(personal_members)
            }

            print(f"📊 发送完成统计: 成功 {success_count}/{len(personal_members)}, 失败 {failed_count}")
            return result_summary

        except Exception as e:
            print(f"向部门成员发送消息异常: {e}")
            return {'success': 0, 'failed': 0, 'total': 0, 'error': str(e)}

    def get_department_contacts(self, department_identifier):
        """Get personal Feishu receive IDs for a department name or department ID."""
        try:
            department_identifier = str(department_identifier or '').strip()
            if not department_identifier:
                return []

            if self._is_department_id(department_identifier):
                return self.get_department_personal_members(department_identifier)

            dept_rows = sf_db(
                f"SELECT FeiShu_ID FROM feishu_id WHERE YONGHU='{self.esc(department_identifier)}' AND (FeiShu_ID LIKE 'od[_]%%' OR FeiShu_ID LIKE 'od-%%')")
            if dept_rows:
                dept_ids = [fid for fid in self._normalize_id_list(dept_rows) if self._is_department_id(fid)]
                for dept_id in dept_ids:
                    members = self.get_department_personal_members(dept_id)
                    if members:
                        return members

            mapped_targets = self._resolve_mapping_targets(department_identifier)
            if mapped_targets:
                print(f"部门 '{department_identifier}' 成员解析失败，使用兜底接收人 {len(mapped_targets)} 个")
                return mapped_targets

            print(f"未找到部门 '{department_identifier}' 对应的 od_ / od- 部门ID")
            return []
        except Exception as e:
            print(f"查询部门联系人异常: {e}")
            return []
    def get_department_members(self, department_id):
        """获取部门成员列表

        Args:
            department_id: 部门ID（以od_开头）

        Returns:
            list: 部门成员的open_id列表
        """
        try:
            access_token = self._get_access_token()
            if not access_token:
                print("❌ 获取token失败，无法获取部门成员")
                return []

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }

            # 调用飞书API获取部门用户列表
            url = "https://open.feishu.cn/open-apis/contact/v3/users"
            params = {
                "user_id_type": "open_id",
                "department_id_type": "open_department_id",
                "department_id": department_id,
                "page_size": 100  # 一次最多获取100个成员
            }

            all_members = []
            page_token = None

            while True:
                if page_token:
                    params["page_token"] = page_token

                response = requests.get(url, headers=headers, params=params)
                result = response.json()

                if result.get('code') != 0:
                    print(f"❌ 获取部门成员失败: {result.get('msg')}")
                    break

                users = result.get('data', {}).get('items', [])
                for user in users:
                    open_id = user.get('open_id')
                    if open_id:
                        all_members.append(open_id)

                # 检查是否还有更多页面
                page_token = result.get('data', {}).get('page_token')
                if not page_token:
                    break

            print(f"✅ 成功获取部门 {department_id} 的 {len(all_members)} 个成员")
            return all_members

        except Exception as e:
            print(f"获取部门成员异常: {e}")
            return []

    def get_department_children(self, department_id):
        try:
            access_token = self._get_access_token()
            if not access_token:
                print("❌ 获取token失败，无法获取子部门")
                return []

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }

            url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children"
            params = {
                "department_id_type": "open_department_id",
                "page_size": 100,
                "fetch_child": False
            }

            all_dept_ids = []
            page_token = None

            while True:
                if page_token:
                    params["page_token"] = page_token

                response = requests.get(url, headers=headers, params=params)
                result = response.json()
                if result.get("code") != 0:
                    print(f"❌ 获取子部门失败: {result.get('msg')}")
                    break

                items = (result.get("data", {}) or {}).get("items", []) or []
                for item in items:
                    did = item.get("open_department_id") or item.get("department_id") or item.get("id")
                    if isinstance(did, str) and self._is_department_id(did):
                        all_dept_ids.append(did)

                page_token = (result.get("data", {}) or {}).get("page_token")
                if not page_token:
                    break

            return all_dept_ids
        except Exception as e:
            print(f"获取子部门异常: {e}")
            return []

    def get_department_with_descendants(self, department_id):
        dept_ids = []
        seen = set()
        stack = [department_id]
        while stack:
            cur = stack.pop()
            if not cur or cur in seen:
                continue
            seen.add(cur)
            dept_ids.append(cur)
            children = self.get_department_children(cur) or []
            for c in children:
                if c and c not in seen:
                    stack.append(c)
        return dept_ids

    def get_department_personal_members(self, department_id):
        """Get all personal open_ids under a department and its descendants."""
        try:
            department_id = str(department_id or '').strip()
            if not department_id:
                return []

            dept_name_rows = sf_db(f"SELECT YONGHU FROM feishu_id WHERE FeiShu_ID='{self.esc(department_id)}'")
            dept_name = department_id
            if dept_name_rows:
                dept_name_values = self._normalize_id_list(dept_name_rows)
                if dept_name_values:
                    dept_name = dept_name_values[0]

            print(f"正在通过飞书API获取部门 '{dept_name}' (ID: {department_id}) 下的成员...")

            dept_ids = self.get_department_with_descendants(department_id)
            all_members = []
            for did in dept_ids:
                members = self.get_department_members(did) or []
                all_members.extend(members)

            personal_members = []
            seen = set()
            for member in all_members:
                if isinstance(member, str) and member.startswith('ou_') and member not in seen:
                    seen.add(member)
                    personal_members.append(member)

            print(f"成功获取部门 '{dept_name}' 下的 {len(personal_members)} 个个人用户")
            return personal_members

        except Exception as e:
            print(f"获取部门个人成员异常: {e}")
            return []
    def send_innovation_notification(self, title, submitter, department, description, target_departments):
        """发送创新提案通知

        Args:
            title: 提案标题
            submitter: 提交者
            department: 提交部门
            description: 提案描述
            target_departments: 目标部门列表

        Returns:
            bool: 发送成功返回True
        """
        try:
            # 构建专业的消息模板
            message_text = f"""🚀 【创新提案通知】

📋 提案标题：{title}
👤 提交人员：{submitter}
🏢 提交部门：{department}
📝 提案描述：{description}
⏰ 提交时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💡 请相关部门及时查看并评估该创新提案，如有疑问请联系提交人员。

感谢您对创新工作的支持！"""

            success_count = 0
            total_contacts = 0

            # 向每个目标部门发送通知
            for dept_name in target_departments:
                # 获取部门联系人
                contacts = self.get_department_contacts(dept_name)
                if not contacts:
                    # 如果没有找到部门联系人，尝试直接发送给部门名称
                    if self.send_message(dept_name, message_text):
                        success_count += 1
                    total_contacts += 1
                else:
                    # 向部门内所有联系人发送
                    for contact in contacts:
                        if self.send_message(contact, message_text):
                            success_count += 1
                        total_contacts += 1

            print(f"创新提案通知发送完成: {success_count}/{total_contacts} 成功")
            return success_count > 0

        except Exception as e:
            print(f"发送创新提案通知异常: {e}")
            return False

    def send_handle_notification(self, title, handler, status, notes, score, submitter=None):
        """发送处理结果通知

        Args:
            title: 提案标题
            handler: 处理人
            status: 处理状态
            notes: 处理备注
            score: 评分
            submitter: 提案提交者（如果提供）

        Returns:
            bool: 发送成功返回True
        """
        try:
            # 状态映射
            status_mapping = {
                'approved': '✅ 已通过',
                'rejected': '❌ 已拒绝',
                'pending': '⏳ 待处理',
                'under_review': '🔍 审核中',
                'completed': '✅ 已完成'
            }
            status_text = status_mapping.get(status, status)

            # 根据状态选择合适的emoji和措辞
            if status == 'approved':
                emoji = '🎉'
                congratulation = '恭喜您的创新提案获得通过！'
            elif status == 'rejected':
                emoji = '💭'
                congratulation = '感谢您的创新提案，请继续关注后续机会。'
            else:
                emoji = '📋'
                congratulation = '感谢您的创新提案！'

            message_text = f"""{emoji} 【创新提案处理结果】

📋 提案标题：{title}
👤 处理人员：{handler}
📊 处理结果：{status_text}
⭐ 评分等级：{score if score else '暂无评分'}
📝 处理意见：{notes if notes else '无特殊说明'}
⏰ 处理时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{congratulation}

如有疑问，请联系相关处理人员。"""

            # 如果提供了提交者信息，发送给提交者；否则发送给处理人
            target = submitter if submitter else handler
            return self.send_message(target, message_text)

        except Exception as e:
            print(f"发送处理结果通知异常: {e}")
            return False

    def send_exchange_notification(self, user_name, reward_name, points_spent, remaining_points=None):
        """发送积分兑换通知

        Args:
            user_name: 用户名
            reward_name: 奖品名称
            points_spent: 消耗积分
            remaining_points: 剩余积分（可选）

        Returns:
            bool: 发送成功返回True
        """
        try:
            # 构建专业的兑换通知消息
            message_text = f"""🎉 【积分兑换成功】

👤 兑换用户：{user_name}
🎁 兑换奖励：{reward_name}
💰 消耗积分：{points_spent} 分
{f'💳 剩余积分：{remaining_points} 分' if remaining_points is not None else ''}
⏰ 兑换时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🎊 恭喜您成功兑换奖励！请按照相关流程领取您的奖励。
继续努力，赚取更多积分兑换更多精彩奖励！"""

            return self.send_message(user_name, message_text)

        except Exception as e:
            print(f"发送积分兑换通知异常: {e}")
            return False

    def send_exchange_notification_renli(self, notice_name,user_name, reward_name, points_spent, remaining_points=None):
        """发送积分兑换通知

        Args:
            user_name: 用户名
            reward_name: 奖品名称
            points_spent: 消耗积分
            remaining_points: 剩余积分（可选）

        Returns:
            bool: 发送成功返回True
        """
        try:
            # 构建专业的兑换通知消息
            message_text = f"""🎉 【用户积分兑换成功】

    👤 兑换用户：{user_name}
    🎁 兑换奖励：{reward_name}
    💰 消耗积分：{points_spent} 分
    {f'💳 剩余积分：{remaining_points} 分' if remaining_points is not None else ''}
    ⏰ 兑换时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    📋 点击链接进入奖品页面查看：http://223.78.73.100:8000 
    🎊 用戶{user_name}成功兑换奖励！请按照相关流程安排对应奖励！！！
"""

            return self.send_message(notice_name, message_text)

        except Exception as e:
            print(f"发送积分兑换通知异常: {e}")
            return False

    def test_connection(self):
        """测试连接

        Returns:
            bool: 连接成功返回True
        """
        try:
            # 直接测试获取访问令牌
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            headers = {"Content-Type": "application/json; charset=utf-8"}
            data = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            return result.get('code') == 0 and 'tenant_access_token' in result
        except Exception as e:
            print(f"测试连接异常: {e}")
            return False


# 创建全局消息服务实例
message_service = MessageService('company1')

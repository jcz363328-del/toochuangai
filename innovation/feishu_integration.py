import requests
import json
from config import FEISHU_CONFIGS, DEPARTMENT_FEISHU_MAPPING


class FeishuBot:
    def __init__(self, company_key=None):
        # 根据公司标识选择配置
        if company_key and company_key in FEISHU_CONFIGS:
            config = FEISHU_CONFIGS[company_key]
        else:
            # 使用默认配置（第一个公司）
            default_key = list(FEISHU_CONFIGS.keys())[0]
            config = FEISHU_CONFIGS[default_key]
            print(f"🏢 使用默认公司配置: {default_key}")

        self.app_id = config['app_id']
        self.app_secret = config['app_secret']
        self.verification_token = config['verification_token']
        self.encrypt_key = config['encrypt_key']
        self.access_token = None
        self.company_key = company_key

    def get_access_token(self):
        """获取访问令牌"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        try:
            print(f"🔄 正在获取access_token...")
            response = requests.post(url, headers=headers, json=data)
            result = response.json()
            print(f"📋 Token获取响应: {result}")

            if result.get('code') == 0:
                self.access_token = result['tenant_access_token']
                print(f"✅ 成功获取access_token: {self.access_token[:20]}...")
                return self.access_token
            else:
                print(f"❌ 获取access_token失败: {result}")
                return None
        except Exception as e:
            print(f"❌ 获取access_token异常: {e}")
            return None

    def send_message(self, receive_id, msg_type="text", content="", receive_id_type=None):
        """发送消息 - 自动识别ID类型"""
        # 自动识别ID类型
        if receive_id_type is None:
            if receive_id.startswith('ou_'):
                receive_id_type = 'user_id'
                print(f"🔍 自动识别为用户ID: {receive_id}")
            elif receive_id.startswith('oc_'):
                receive_id_type = 'chat_id'
                print(f"🔍 自动识别为群聊ID: {receive_id}")
            elif receive_id.startswith('od_'):
                receive_id_type = 'open_id'
                print(f"🔍 自动识别为开放ID: {receive_id}")
            else:
                print(f"❌ 无法识别ID类型: {receive_id}")
                return None

        # 每次发送消息前都重新获取token，确保token有效
        token = self.get_access_token()
        if not token:
            print("❌ 无法获取有效的access_token")
            return None

        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        # 根据消息类型处理content
        if msg_type == "text":
            message_content = json.dumps({"text": content})
        elif msg_type == "interactive":
            message_content = content  # 卡片消息content已经是JSON字符串
        else:
            message_content = content

        data = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": message_content
        }

        params = {"receive_id_type": receive_id_type}

        try:
            print(f"🔄 正在发送消息到 {receive_id} (类型: {receive_id_type})")
            print(f"📋 请求URL: {url}")
            print(f"📋 请求头: {headers}")
            print(f"📋 请求参数: {params}")
            print(f"📋 请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")

            response = requests.post(url, headers=headers, json=data, params=params)
            result = response.json()

            print(f"📋 响应状态码: {response.status_code}")
            print(f"📋 响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")

            return result
        except Exception as e:
            print(f"❌ 发送消息异常: {e}")
            return None

    def send_message_to_user(self, user_id, msg_type="text", content=""):
        """发送消息到用户"""
        print(f"🔄 准备向用户发送消息: {user_id}")
        return self.send_message(user_id, msg_type, content, "user_id")

    def send_message_to_group(self, group_id, msg_type="text", content=""):
        """发送消息到群组或用户（自动识别）"""
        print(f"🔄 准备发送消息: {group_id}")
        return self.send_message(group_id, msg_type, content)  # 自动识别ID类型


    def send_innovation_notification(self, title, department, content, initiator, deadline=None):
        """发送创新项目通知给承接部门"""
        print(f"🔄 准备发送创新项目通知: {title} -> {department}")

        # 获取部门对应的ID（部门负责人的用户ID）
        target_id = DEPARTMENT_FEISHU_MAPPING.get(department)
        if not target_id:
            print(f"❌ 未找到部门 {department} 对应的ID")
            print(f"📋 可用的部门映射: {list(DEPARTMENT_FEISHU_MAPPING.keys())}")
            return None

        # 处理列表格式的多个接收者
        if isinstance(target_id, list):
            target_ids = target_id
            print(f"📋 找到多个目标ID: {target_ids}")
        else:
            target_ids = [target_id]
            print(f"📋 找到目标ID: {target_id}")

        # 构建通知消息，包含截止时间信息和管理页面链接
        deadline_text = f"\n截止时间：{deadline}" if deadline else ""
        manage_url = "http://223.78.73.100:8000/innovation/manage"  # 可以从配置文件中获取
        test_message = f"""🚀 新的创新项目待承接

    项目标题：{title}
    承接部门：{department}
    发起人：{initiator}{deadline_text}

    项目内容：
    {content}

    📋 点击链接进入管理页面处理：
    {manage_url}"""

        # 向所有接收者发送消息
        results = []
        for tid in target_ids:
            result = self.send_message(tid, "text", test_message, "user_id")
            results.append(result)

            if result and result.get('code') == 0:
                print(f"✅ 成功向 {department} 的接收者 {tid} 发送项目通知")
            else:
                print(f"❌ 向 {department} 的接收者 {tid} 发送通知失败: {result}")

        return results

    def send_status_update_notification(self, title, status, handler, score, initiator_department):
        """发送项目状态更新通知给发起人部门"""
        print(f"🔄 准备发送状态更新通知: {title} -> {initiator_department}")

        # 获取发起人部门对应的ID
        target_id = DEPARTMENT_FEISHU_MAPPING.get(initiator_department)
        if not target_id:
            print(f"❌ 未找到发起人部门 {initiator_department} 对应的ID")
            print(f"📋 可用的部门映射: {list(DEPARTMENT_FEISHU_MAPPING.keys())}")
            return None

        # 处理列表格式的多个接收者
        if isinstance(target_id, list):
            target_ids = target_id
            print(f"📋 找到多个目标ID: {target_ids}")
        else:
            target_ids = [target_id]
            print(f"📋 找到目标ID: {target_id}")

        # 发送状态更新文本消息，包含管理页面链接
        score_text = f"\n项目评分：{score}/10分" if score and score > 0 else ""
        manage_url = "http://223.78.73.100:8000/innovation/manage"  # 可以从配置文件中获取
        status_message = f"""📋 项目状态更新通知

    项目标题：{title}
    处理状态：{status}
    处理人：{handler}{score_text}

    感谢您的参与！

    📋 查看更多项目详情：
    {manage_url}"""

        # 向所有接收者发送消息
        results = []
        for tid in target_ids:
            result = self.send_message_to_group(tid, "text", status_message)
            results.append(result)

            if result and result.get('code') == 0:
                print(f"✅ 成功向发起人部门 {initiator_department} 的接收者 {tid} 发送状态更新通知")
            else:
                print(f"❌ 向发起人部门 {initiator_department} 的接收者 {tid} 发送通知失败: {result}")

        return results

    def create_innovation_card(self, title, department, content, initiator, card_type="new"):
        """创建创新项目卡片消息"""
        if card_type == "new":
            header_title = "🚀 新的创新项目待承接"
            header_color = "blue"
            button_text = "立即承接"
            tip_text = "💡 **温馨提示：** 请及时承接并处理项目，完成后记得进行评分反馈"
        else:
            header_title = "📋 项目状态更新"
            header_color = "green"
            button_text = "查看详情"
            tip_text = "📬 您的创新项目状态已更新，感谢您的参与！"

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": f"**项目标题：** {title}\n**承接部门：** {department}\n**发起人：** {initiator}\n\n**项目内容：**\n{content}",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": tip_text,
                        "tag": "lark_md"
                    }
                },
                {
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "content": button_text,
                                "tag": "plain_text"
                            },
                            "type": "primary",
                            "url": "http://localhost:8080/manage"  # 替换为实际的管理页面URL
                        }
                    ],
                    "tag": "action"
                }
            ],
            "header": {
                "template": header_color,
                "title": {
                    "content": header_title,
                    "tag": "plain_text"
                }
            }
        }

        return json.dumps(card)

    def create_status_update_card(self, title, status, handler, score):
        """创建状态更新卡片消息"""
        status_emoji = {
            "进行中": "🔄",
            "已完成": "✅",
            "已拒绝": "❌",
            "已取消": "⏹️"
        }

        score_text = f"\n**项目评分：** {score}/10分" if score and score > 0 else ""

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": f"**项目标题：** {title}\n**处理状态：** {status_emoji.get(status, '📋')} {status}\n**处理人：** {handler}{score_text}",
                        "tag": "lark_md"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "content": "📬 您的创新项目状态已更新，感谢您的参与！",
                        "tag": "lark_md"
                    }
                },
                {
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "content": "查看详情",
                                "tag": "plain_text"
                            },
                            "type": "default",
                            "url": "http://localhost:8080/manage"  # 替换为实际的管理页面URL
                        }
                    ],
                    "tag": "action"
                }
            ],
            "header": {
                "template": "green",
                "title": {
                    "content": "📋 项目状态更新通知",
                    "tag": "plain_text"
                }
            }
        }

        return json.dumps(card)

    def send_innovation_card(self, title, department, content, initiator):
        """发送创新项目卡片消息（兼容旧版本）"""
        return self.send_innovation_notification(title, department, content, initiator)

    def create_card_message(self, title, department, content, initiator):
        """创建卡片消息内容（兼容旧版本）"""
        return self.create_innovation_card(title, department, content, initiator, "new")

    def test_connection(self):
        """测试飞书连接"""
        print("=== 飞书连接测试 ===")
        token = self.get_access_token()
        if token:
            print("✅ 飞书连接成功")
            print(f"Access Token: {token[:20]}...")

            # 测试发送消息到AI部
            print("\n=== 测试发送消息 ===")
            test_department = "AI部"
            target_id = DEPARTMENT_FEISHU_MAPPING.get(test_department)

            if target_id:
                result = self.send_message_to_group(target_id, "text", "🧪 这是一条测试消息，用于验证飞书通知功能")
                if result and result.get('code') == 0:
                    print(f"✅ 测试消息发送成功")
                    return True
                else:
                    print(f"❌ 测试消息发送失败: {result}")
                    return False
            else:
                print(f"❌ 未找到 {test_department} 的ID")
                return False
        else:
            print("❌ 飞书连接失败")
            return False

    def send_card_notification(self, title, department, content, initiator):
        """发送卡片通知（如果文本消息成功，可以尝试卡片消息）"""
        print(f"🔄 准备发送卡片通知: {title} -> {department}")

        # 获取部门对应的ID
        target_id = DEPARTMENT_FEISHU_MAPPING.get(department)
        if not target_id:
            print(f"❌ 未找到部门 {department} 对应的ID")
            return None

        # 处理列表格式的多个接收者
        if isinstance(target_id, list):
            target_ids = target_id
            print(f"📋 找到多个目标ID: {target_ids}")
        else:
            target_ids = [target_id]
            print(f"📋 找到目标ID: {target_id}")

        # 创建卡片消息
        card_content = self.create_innovation_card(title, department, content, initiator, "new")

        # 向所有接收者发送消息
        results = []
        for tid in target_ids:
            result = self.send_message_to_group(tid, "interactive", card_content)
            results.append(result)

            if result and result.get('code') == 0:
                print(f"✅ 成功向 {department} 的接收者 {tid} 发送卡片通知")
            else:
                print(f"❌ 向 {department} 的接收者 {tid} 发送卡片通知失败: {result}")
                # 如果卡片消息失败，回退到文本消息
                print(f"🔄 为接收者 {tid} 回退到文本消息...")
                fallback_result = self.send_innovation_notification(title, department, content, initiator)
                if fallback_result:
                    results[-1] = fallback_result  # 替换失败的结果

        return results


    def send_exchange_notification(self, user_name, reward_name, points_spent, exchange_time=None):
        """发送积分兑换通知给人力部门"""
        try:
            print(f"🔄 准备发送积分兑换通知: {user_name} 兑换 {reward_name}")

            # 从配置中获取人力行政部的ID
            hr_department = "人力行政部"
            target_id = DEPARTMENT_FEISHU_MAPPING.get(hr_department)

            if not target_id:
                print(f"❌ 未找到 {hr_department} 对应的ID")
                print(f"📋 可用的部门映射: {list(DEPARTMENT_FEISHU_MAPPING.keys())}")
                return False

            # 处理列表格式的多个接收者
            if isinstance(target_id, list):
                target_ids = target_id
                print(f"📋 找到多个目标ID: {target_ids}")
            else:
                target_ids = [target_id]
                print(f"📋 找到目标ID: {target_id}")

            # 如果没有提供兑换时间，使用当前时间
            if not exchange_time:
                from datetime import datetime
                exchange_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 构建通知消息
            message = f"""🎁 积分兑换通知

    兑换人员：{user_name}
    兑换奖品：{reward_name}
    消耗积分：{points_spent}
    兑换时间：{exchange_time}

    请人力部门及时安排奖品发放。"""

            # 向所有接收者发送消息
            results = []
            for tid in target_ids:
                print(f"🔄 向接收者 {tid} 发送兑换通知...")
                result = self.send_message(tid, "text", message, "user_id")
                results.append(result)

                if result and result.get('code') == 0:
                    print(f"✅ 成功向 {hr_department} 的接收者 {tid} 发送兑换通知")
                else:
                    print(f"❌ 向 {hr_department} 的接收者 {tid} 发送通知失败: {result}")

            # 如果至少有一个成功，返回True
            success_count = sum(1 for r in results if r and r.get('code') == 0)
            if success_count > 0:
                print(f"✅ 积分兑换通知发送完成，成功 {success_count}/{len(results)} 个接收者")
                return True
            else:
                print(f"❌ 积分兑换通知发送失败，所有接收者都失败")
                return False

        except Exception as e:
            print(f"❌ 积分兑换通知发送异常: {e}")
            import traceback
            print(f"❌ 异常详情: {traceback.format_exc()}")
            return False
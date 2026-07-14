
#############################################################################
import pytds as sql  # pip install python-tds -i https://pypi.tuna.tsinghua.edu.cn/simple，可能得在3.10版本中才能使用
import pandas as pd
import requests
import hashlib
import time
from secret_settings import baidu_translate_config, get_feishu_message_config, sql_server_config
############################################################################
def sf_db(SQL, single=False):
    # 开发日期：2025-05-05
    # 功能：实现对数据库的select操作。sf=select from
    # 参数说明：
    #     SQL：SQL语句
    #  single：默认或者False时，返回列表，每个元素为元组，为True时返回单个值
    con = sql.connect(**sql_server_config())
    cursor = con.cursor()
    cursor.execute(SQL)
    rs = cursor.fetchall()

    if not rs or len(rs) == 0:                      # 修复：检查结果集是否为空
        con.close()
        return [] if not single else None

    if single == False:
        if len(rs[0]) == 1:                         # 当single==False时，如果返回的结果只有一列，就直接转化为列表，避免列表里面套元组
            myList = []
            for e in rs:
                myList.append(e[0])
            con.close()
            return myList
        else:
            con.close()
            return rs
    else:
        con.close()
        return rs[0][0]


#########################################################################
def dui_db(SQL,show_result=False):
    # 开发日期：2025-05-05
    # 功能：实现对数据库的update、delete、insert操作。dui=delete、update、insert
    # 参数说明：
    #         SQL：SQL语句
    # show_result：是否显示影响了多少条数据

    conn = sql.connect(**sql_server_config())
    cursor = conn.cursor()                      # 创建游标
    cursor.execute(SQL)

    if show_result==True:
        print(f"更新了 {cursor.rowcount} 条记录")
    if not conn.autocommit:
        conn.commit()


########################################################################
def get_cname():
    # 获取本机计算机名
    import socket
    return socket.getfqdn(socket.gethostname())


######################################################################
def text_to_file(s,fullpath):
    # 开发日期：2025-04-14
    # 功能：将指定的字符串写入到指定的txt文件中
    f=open(fullpath,'a')                        # 打开文件以便写入，a:追加append，w：写入write
    print(s,file=f)
    f.close()


######################################################################
def append_to_file(content,file_path):
    # 功能：将字符串追加写入到指定的文本文件中（不覆盖原有内容）
    # 参数说明：
    #   content: 要追加的字符串
    # file_path: 完整的目标文件路径
    with open(file_path, mode='a', encoding='utf-8') as file:
        file.write(content)


######################################################################
def baidu_translate(text: str) -> str:
    '''英文翻译中文'''
    # ========== 配置 ==========
    translate_cfg = baidu_translate_config()
    APP_ID = translate_cfg["app_id"]###百度翻译id
    SECRET_KEY = translate_cfg["secret_key"]#####百度翻译秘钥
    FROM_LANG = 'en'
    TO_LANG = 'zh'
    API_URL = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    if pd.isna(text) or str(text).strip() == '':
        return ''

    text = str(text).strip()
    salt = str(int(time.time() * 1000))  # 毫秒级 salt
    sign_str = APP_ID + text + salt + SECRET_KEY
    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

    params = {
        'q': text,
        'from': FROM_LANG,
        'to': TO_LANG,
        'appid': APP_ID,
        'salt': salt,
        'sign': sign
    }

    try:
        resp = requests.get(API_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data['trans_result'][0]['dst']
    except Exception as e:
        print(f'翻译失败：{text} -> {e}')
        return '翻译失败'


###################################################################
def get_user_accessible_skus(lei_xing=1):
    # 获取当前电脑用户可以访问的SKU列表
    # 返回：可访问的SKU列表
    computer_name = get_cname()
    sql_query = f"""
    SELECT distinct ZhuSKU 
      FROM ZiDian 
     WHERE Dian in (SELECT Dian 
                      FROM DianQuanXian 
                     WHERE LeiXing={lei_xing} and YunYing=(SELECT UName
                                                    FROM ComputerName
                                                   WHERE cname='{computer_name}'))
    """
    try:
        accessible_skus = sf_db(sql_query)
        return accessible_skus
    except Exception as e:
        print(f"获取用户权限失败：{e}")
        return []


def sku_yunxu(sku,lei_xing=1):
    # 功能检查当前用户是否有权限访问指定的SKU
    # 参数：
    #        sku：要检查的SKU
    #   lei_xing：1权限或者2权限，默认为1

    computer_name = get_cname()
    s=f"""SELECT count(*) 
            FROM ZiDian
           WHERE SKU='{sku}'  
                 and Dian in (SELECT Dian 
                                FROM DianQuanXian 
                               WHERE LeiXing={lei_xing}
                                     and YunYing=(SELECT UName
                                                    FROM ComputerName
                                                   WHERE cname='{computer_name}'))
        """
    return int(sf_db(s,True))>0


def get_filtered_data_by_permission(base_sql, sku_column='ZhuSKU'):
    '''
    根据用户权限过滤数据查询结果
    参数：
        base_sql - 基础SQL查询语句
        sku_column - SKU字段名，默认为'ZhuSKU'
    返回：过滤后的查询结果
    '''
    accessible_skus = get_user_accessible_skus()

    if not accessible_skus:
        print("当前用户没有任何SKU访问权限")
        return []

    # 构建SKU权限过滤条件
    sku_filter = "','".join(accessible_skus)

    # 在原SQL基础上添加权限过滤
    if 'where' in base_sql.lower():
        filtered_sql = f"{base_sql} AND {sku_column} IN ('{sku_filter}')"
    else:
        filtered_sql = f"{base_sql} WHERE {sku_column} IN ('{sku_filter}')"

    try:
        return sf_db(filtered_sql)
    except Exception as e:
        print(f"权限过滤查询失败：{e}")
        return []


def show_user_permissions():
    '''
    显示当前用户的权限信息
    '''
    computer_name = get_cname()
    accessible_skus = get_user_accessible_skus()

    print(f"当前电脑名称：{computer_name}")
    print(f"可访问的SKU数量：{len(accessible_skus)}")

    if accessible_skus:
        print("可访问的SKU列表：")
        for i, sku in enumerate(accessible_skus, 1):
            print(f"  {i}. {sku}")
    else:
        print("当前用户没有任何SKU访问权限")
####################################################################
    import hashlib
    import base64
    from urllib.parse import quote
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.backends import default_backend

    def aes_encrypt_ecb_pkcs5(text, key):
        """使用cryptography库实现AES/ECB/PKCS5PADDING加密"""
        try:
            # 确保密钥长度为16字节（128位）
            if len(key) > 16:
                key = key[:16]
            elif len(key) < 16:
                key = key.ljust(16, '\0')

            key_bytes = key.encode('utf-8')
            text_bytes = text.encode('utf-8')

            # 创建AES加密器，使用ECB模式
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB(), backend=default_backend())
            encryptor = cipher.encryptor()

            # PKCS5PADDING填充
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(text_bytes)
            padded_data += padder.finalize()

            # 加密
            encrypted = encryptor.update(padded_data) + encryptor.finalize()

            # Base64编码
            encrypted_base64 = base64.b64encode(encrypted).decode('utf-8')
            return encrypted_base64

        except Exception as e:
            print(f"AES加密失败: {e}")
            return None

    def generate_sign_complete(params, app_id):
        """生成完整的签名（MD5 + AES/ECB/PKCS5PADDING + URL编码）

        Args:
            params (dict): 需要签名的参数字典
            app_id (str): 应用ID，用作AES加密密钥

        Returns:
            str: 最终签名字符串，如果失败返回None
        """
        try:
            print("\n=== 完整签名生成过程 ===")

            # 1. 过滤空值参数
            filtered_params = {}
            for key, value in params.items():
                if value is not None and value != '':
                    filtered_params[key] = value

            print(f"过滤后参数: {filtered_params}")

            # 2. 按ASCII排序
            sorted_keys = sorted(filtered_params.keys())
            print(f"排序后的键: {sorted_keys}")

            # 3. 拼接为key=value格式
            param_string = '&'.join([f"{key}={filtered_params[key]}" for key in sorted_keys])
            print(f"拼接字符串: {param_string}")

            # 4. MD5加密并转大写（关键修复）
            md5_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest().upper()
            print(f"MD5结果: {md5_hash}")

            # 5. AES加密（使用app_id作为密钥，关键修复）
            aes_result = aes_encrypt_ecb_pkcs5(md5_hash, app_id)
            print(f"AES加密结果: {aes_result}")

            # 6. URL编码
            final_sign = quote(aes_result, safe='')
            print(f"最终签名: {final_sign}")

            return final_sign

        except Exception as e:
            print(f"签名生成失败: {e}")
            return None

#################################################################
def db_to_dic(sql,delimiter='@'):
    '''
    开发日期：2025-08-14
    功能：指定SQL语句，将第一列作为Key值，之后所有的列作为Value值，用指定的拼接符链接，返回字典
    '''
    l=sf_db(sql)                                    # 列表，里面嵌套元组
    mydic={}
    for ele in l:
        s = ''
        for i in range(1,len(ele)):                 # 将每个元组中从第2个元素开始，拼接起来
            s = s + str(ele[i]) + delimiter
        s=s[0:len(s)-len(delimiter)]                # 去掉最后面的连接符
        mydic[str(ele[0])]=s                        # 键值对添加到字典中
    return mydic


#################################################################
def driver_number(driver='C'):
    # 开发日期：2025-08-19
    # 功能：返回指定盘符的序列号，默认为C盘
    import ctypes
    vol_name_buf = ctypes.create_unicode_buffer(1024)
    fs_name_buf = ctypes.create_unicode_buffer(1024)
    serial_number = ctypes.c_ulong()
    flags = ctypes.c_ulong()
    max_component_length = ctypes.c_ulong()
    res = ctypes.windll.kernel32.GetVolumeInformationW(
          ctypes.c_wchar_p(driver+":\\"),vol_name_buf,
          ctypes.sizeof(vol_name_buf),ctypes.byref(serial_number),
          ctypes.byref(max_component_length),ctypes.byref(flags),
          fs_name_buf,ctypes.sizeof(fs_name_buf))

    if res == 0:raise ctypes.WinError()
    if serial_number.value >= 2**31:return abs(serial_number.value - 2**32)
    return abs(serial_number.value)


#########################################################################
def today(n=0):
    # 开发日期：2025-8-18
    # 功能：如果n=0或者默认，返回今天的日期；
    #      如果n<0，则返回今天之前n天的日期；
    #      如果n>0，返回今天n天之后的日期
    from datetime import datetime, timedelta
    return datetime.now().date()+timedelta(days=n)

def date_delta(mydate,n):
    # 开发日期：2025-08-18
    # 功能：给定日期，返回该日期+n之后的日期
    from datetime import datetime, timedelta
    return mydate + timedelta(days=n)

############################################################################
import os
import requests
import json
import time

from bjc import *
import os, json, requests


def send_message(chat_name, message, image_path=None):
    """
    发送图文混合消息到飞书（个人或群组）
    chat_name:
        - 表 feishu_id.YONGHU（查库找 FeiShu_ID）
        - 或直接传 FeiShu_ID (oc_/ou_/od_/ou_) 或邮箱
    """

    def esc(v): return '' if v is None else str(v).replace("'", "''")

    def detect_type(fid: str):
        if fid.startswith("oc_"): return "chat_id"
        if fid.startswith("ou_"): return "user_id"
        if fid.startswith("od_"): return "open_id"
        if "@" in fid: return "email"
        return "user_id"  # 默认 employee_id

    if not (chat_name and message):
        print("❌ 参数缺失"); return False

    # 获取 FeiShu_ID
    if chat_name.startswith(("oc_", "ou_", "od_")) or "@" in chat_name:
        ids = [chat_name]
    else:
        rows = sf_db(f"SELECT FeiShu_ID FROM feishu_id WHERE YONGHU='{esc(chat_name)}'")
        if not rows: return False
        ids = rows if isinstance(rows, list) else [rows]

    # 获取 token
    feishu_config = get_feishu_message_config()
    r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": feishu_config["app_id"], "app_secret": feishu_config["app_secret"]})
    access_token = r.json().get("tenant_access_token")
    if not access_token: return False

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=utf-8"}
    msg_url, img_url = "https://open.feishu.cn/open-apis/im/v1/messages", "https://open.feishu.cn/open-apis/im/v1/images"

    # 图片上传
    image_key = None
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            files, data = {"image": (os.path.basename(image_path), f, "image/png")}, {"image_type": "message"}
            resp = requests.post(img_url, headers={"Authorization": f"Bearer {access_token}"}, files=files, data=data).json()
            image_key = resp.get("data", {}).get("image_key")

    # 发消息
    all_ok = True
    for fid in ids:
        rtype = detect_type(str(fid))
        payload = {"receive_id": fid, "msg_type": "text", "content": json.dumps({"text": message}, ensure_ascii=False)}
        if requests.post(f"{msg_url}?receive_id_type={rtype}", headers=headers, json=payload).json().get("code") != 0:
            all_ok = False
        if image_key:
            payload = {"receive_id": fid, "msg_type": "image", "content": json.dumps({"image_key": image_key})}
            if requests.post(f"{msg_url}?receive_id_type={rtype}", headers=headers, json=payload).json().get("code") != 0:
                all_ok = False

    # 日志
    if all_ok:
        sql = (f"INSERT INTO FaYouJian VALUES('飞书消息推送','{esc(chat_name)}->{','.join(ids)}',"
               f"'飞书消息','{esc(message)}',GETDATE(),'123456789',GETDATE())")
        dui_db(sql, show_result=True)
    return all_ok
###################################################################################################
import os
import requests
import json
from bjc import *

def send_message(chat_name, message, at_users=None, at_all=False, image_paths=None):
    """
    chat_name   : feishu_id.YONGHU （数据库查 FeiShu_ID，群或人）
    message     : 消息文本
    at_users    : @的人名字列表（从feishu_id表查 FeiShu_ID，必须是 ou_xxx）
    at_all      : True 表示 @所有人
    image_paths : 图片路径列表（可以多张），默认 None
    """

    def esc(v): return '' if v is None else str(v).replace("'", "''")

    # ========= 从数据库查 chat_id / user_id =========
    rows = sf_db(f"SELECT FeiShu_ID FROM feishu_id WHERE YONGHU='{esc(chat_name)}'")
    if not rows:
        print(f"❌ 未找到 {chat_name} 的 FeiShu_ID，请确认 feishu_id 表有记录")
        return False
    fid = rows if isinstance(rows, str) else rows[0]

    # ========= 获取 token =========
    feishu_config = get_feishu_message_config()
    r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": feishu_config["app_id"],
                            "app_secret": feishu_config["app_secret"]})
    access_token = r.json().get("tenant_access_token")
    if not access_token:
        print("❌ 获取 token 失败", r.json())
        return False

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=utf-8"}
    msg_url = "https://open.feishu.cn/open-apis/im/v1/messages"
    img_url = "https://open.feishu.cn/open-apis/im/v1/images"

    # ========= 构建文本 / @消息 =========
    if at_users or at_all:
        # 查 open_id
        elements = [{"tag": "text", "text": message + " "}]

        if at_users:
            for uname in at_users:
                row2 = sf_db(f"SELECT FeiShu_ID FROM feishu_id WHERE YONGHU='{esc(uname)}'")
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
                    "content": [elements]   # ✅ title 去掉了
                }
            }, ensure_ascii=False)
        }
    else:
        payload = {"receive_id": fid, "msg_type": "text", "content": json.dumps({"text": message}, ensure_ascii=False)}

    # ========= 发送文字 / @消息 =========
    r = requests.post(
        f"{msg_url}?receive_id_type={'chat_id' if fid.startswith('oc_') else 'open_id'}",
        headers=headers, json=payload
    ).json()
    print("➡️ 文本/AT 发送结果:", r)
    success = r.get("code") == 0

    # ========= 发送图片（多张） =========
    if image_paths:
        for img in image_paths:
            if not os.path.exists(img):
                print(f"⚠️ 图片不存在: {img}")
                continue
            with open(img, "rb") as f:
                files = {"image": (os.path.basename(img), f, "image/png")}
                data = {"image_type": "message"}
                resp = requests.post(img_url, headers={"Authorization": f"Bearer {access_token}"}, files=files, data=data).json()
                image_key = resp.get("data", {}).get("image_key")
                if image_key:
                    img_payload = {"receive_id": fid, "msg_type": "image", "content": json.dumps({"image_key": image_key})}
                    r2 = requests.post(
                        f"{msg_url}?receive_id_type={'chat_id' if fid.startswith('oc_') else 'open_id'}",
                        headers=headers, json=img_payload
                    ).json()
                    print(f"➡️ 图片 {img} 发送结果:", r2)
                    success = success and (r2.get("code") == 0)

    return success

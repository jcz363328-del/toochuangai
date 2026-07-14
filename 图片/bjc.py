
#############################################################################
import pytds as sql  # pip install python-tds -i https://pypi.tuna.tsinghua.edu.cn/simple，可能得在3.10版本中才能使用
import pytds
import pandas as pd
import requests
import hashlib
import time
import json
import datetime
import os
import sys
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from secret_settings import baidu_translate_config, get_feishu_message_config, sql_server_config
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

DB_CONFIG = sql_server_config()
DB_LOCK_TIMEOUT_MS = 5000
DB_MAX_RETRIES = 3
DB_RETRY_BASE_SECONDS = 0.5


def _db_connect():
    return sql.connect(**DB_CONFIG)


def _set_lock_timeout(cursor):
    try:
        cursor.execute(f"SET LOCK_TIMEOUT {DB_LOCK_TIMEOUT_MS}")
    except Exception:
        pass


def _is_retryable_db_error(err):
    msg = str(err).lower()
    return (
        "1205" in msg
        or "deadlock" in msg
        or "lock request time out period exceeded" in msg
        or "timeout" in msg
    )


def _close_db(conn=None, cursor=None):
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            pass
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

#########################################################################
def sf_db(SQL, *_unused_args):
    # 开发日期：2025-05-05
    # 功能：实现对数据库的select操作。sf=select from
    # 参数说明：
    #     SQL：SQL语句
    for attempt in range(DB_MAX_RETRIES):
        con = None
        cursor = None
        try:
            con = _db_connect()
            cursor = con.cursor()
            _set_lock_timeout(cursor)
            cursor.execute(SQL)
            rs = cursor.fetchall()                  # rs是个列表，里面每个元素是一个元组

            if not rs or len(rs) == 0:             # 检查结果集是否为空
                return []

            if len(rs) == 1 and len(rs[0]) == 1:   # 返回单个值
                return rs[0][0]

            if len(rs[0]) == 1:                    # 单列结果转成一维列表
                return [e[0] for e in rs]
            return rs                              # 直接返回列表
        except Exception as e:
            need_retry = (attempt < DB_MAX_RETRIES - 1) and _is_retryable_db_error(e)
            if not need_retry:
                raise
            wait_seconds = DB_RETRY_BASE_SECONDS * (2 ** attempt)
            print(f"sf_db重试({attempt + 1}/{DB_MAX_RETRIES})，原因：{e}")
            time.sleep(wait_seconds)
        finally:
            _close_db(con, cursor)


#########################################################################
def dui_db(SQL,show_result=False):
    # 开发日期：2025-05-05
    # 功能：实现对数据库的update、delete、insert操作。dui=delete、update、insert
    # 参数说明：
    #         SQL：SQL语句
    # show_result：是否显示影响了多少条数据

    for attempt in range(DB_MAX_RETRIES):
        conn = None
        cursor = None
        try:
            conn = _db_connect()
            cursor = conn.cursor()                      # 创建游标
            _set_lock_timeout(cursor)
            cursor.execute(SQL)

            if show_result==True:
                print(f"更新了 {cursor.rowcount} 条记录")
            if not conn.autocommit:
                conn.commit()
            return
        except Exception as e:
            if conn is not None and not getattr(conn, "autocommit", True):
                try:
                    conn.rollback()
                except Exception:
                    pass
            need_retry = (attempt < DB_MAX_RETRIES - 1) and _is_retryable_db_error(e)
            if not need_retry:
                raise
            wait_seconds = DB_RETRY_BASE_SECONDS * (2 ** attempt)
            print(f"dui_db重试({attempt + 1}/{DB_MAX_RETRIES})，原因：{e}")
            time.sleep(wait_seconds)
        finally:
            _close_db(conn, cursor)


#########################################################################
def get_cname():
    # 获取本机计算机名
    import socket
    return socket.getfqdn(socket.gethostname())

#########################################################################
def get_uname():
    """开发日期：2025-09-15
       功能：获取当前用户名
    """
    s=f"SELECT UName FROM ComputerName WHERE CName='{get_cname()}'"
    return sf_db(s)

#########################################################################
def text_to_file(s,fullpath):
    # 开发日期：2025-04-14
    # 功能：将指定的字符串写入到指定的txt文件中
    f=open(fullpath,'a', encoding='utf-8')                        # 打开文件以便写入，a:追加append，w：写入write
    print(s,file=f)
    f.close()

#########################################################################
def append_to_file(content,file_path):
    # 功能：将字符串追加写入到指定的文本文件中（不覆盖原有内容）
    # 参数说明：
    #   content: 要追加的字符串
    # file_path: 完整的目标文件路径
    with open(file_path, mode='a', encoding='utf-8') as file:
        file.write(content)

#########################################################################
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

    params = {'q': text,
           'from': FROM_LANG,
             'to': TO_LANG,
          'appid': APP_ID,
           'salt': salt,
           'sign': sign}

    try:
        resp = requests.get(API_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data['trans_result'][0]['dst']
    except Exception as e:
        print(f'翻译失败：{text} -> {e}')
        return '翻译失败'

#########################################################################
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

#########################################################################
def sku_yunxu(sku,lei_xing=1):
    # 功能检查当前用户是否有权限访问指定的SKU
    # 参数：
    #        sku：要检查的SKU
    #   lei_xing：1权限或者2权限，默认为1

    cn = get_cname()
    s=f"""SELECT count(*) 
            FROM ZiDian
           WHERE SKU='{sku}'  
                 and Dian in (SELECT Dian 
                                FROM DianQuanXian 
                               WHERE LeiXing={lei_xing}
                                     and YunYing=(SELECT UName
                                                    FROM ComputerName
                                                   WHERE cname='{cn}'))
        """
    return int(sf_db(s))>0

#########################################################################
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

#########################################################################
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

#########################################################################
def db_to_dic(sql,delimiter='@'):
    '''
    开发日期：2025-08-14
    功能：指定SQL语句，将第一列作为Key值，之后所有的列作为Value值，用指定的拼接符链接，返回字典
          如果SQL只返回1列，用这一列作为key，用''作为value
    '''
    l=sf_db(sql)                                    # 列表，里面嵌套元组
    mydic={}
    if isinstance(l[0], tuple):                     # 如果返回的l中的每个元素是元组，则说明返回的是多列数据
        for ele in l:                               # 将每个元组的第一个元素作为key，其他的元素拼接起来作为value
            s = ''
            for i in range(1,len(ele)):             # 将每个元组中从第2个元素开始，拼接起来
                s = s + str(ele[i]) + delimiter
            s=s[0:len(s)-len(delimiter)]            # 去掉最后面的连接符
            mydic[ele[0]] = s                       # 键值对添加到字典中
    else:                                           # 如果返回的l中的每个元素是字符串，则说明返回的是单列数据，用''作为value值
        for ele in l: mydic[ele]=''
    return mydic

#########################################################################
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

#########################################################################
def date_delta(mydate,n):
    # 开发日期：2025-08-18
    # 功能：给定日期，返回该日期+n之后的日期
    from datetime import datetime, timedelta
    return mydate + timedelta(days=n)

#########################################################################
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
    rows = sf_db(f"SELECT FeiShu_ID FROM FeiShu_ID WHERE YongHu='{esc(chat_name)}'")
    if not rows:
        print(f"❌ 未找到 {chat_name} 的 FeiShu_ID，请确认 FeiShu_ID 表有记录")
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
                    "content": [elements]
                }
            }, ensure_ascii=False)
        }
    else:
        payload = {"receive_id": fid, "msg_type": "text", "content": json.dumps({"text": message}, ensure_ascii=False)}

    # ========= 发送文字 / @消息 =========
    r = requests.post(
        f"{msg_url}?receive_id_type={'chat_id' if fid.startswith('oc_') else 'open_id'}",
        headers=headers, json=payload).json()
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
                        headers=headers, json=img_payload).json()
                    print(f"➡️ 图片 {img} 发送结果:", r2)
                    success = success and (r2.get("code") == 0)

    return success

#########################################################################
def 申请发邮件(收件人,标题,正文,申请人=''):
    """开发日期：2025-09-15
           功能：往FaYouJian中写入数据，申请发邮件
    """
    if 申请人=='': 申请人=get_cname() + '@' + get_uname()
    s=f"INSERT INTO FaYouJian VALUES('{申请人}','{收件人}','{标题}','{正文}',getdate(),'','')"
    dui_db(s)

#########################################################################
def 获取邮箱(用户):
    """开发日期：2025-09-15
           功能：给定一个或多个用户，返回对应的邮箱
    """
    dic=db_to_dic(f"SELECT * FROM v_YouXiang WHERE UName<>''")   # 获取到所有的邮箱

    s=''
    if isinstance(用户,str): 用户=[用户]                          # 强制转换成列表，以适应只给定一个用户的情况
    for yh in 用户:
        if yh in dic: s = s + dic[yh] + ';'
    return s[0:-1]

#########################################################################
def 获取参数值(参数名):
    """开发日期：2025-09-15
           功能：给定参数名，从数据库的YouJianTongZhi返回参数值
    """
    s=f"select ShouJianRen from YouJianTongZhi WHERE ShiXiang='{参数名}'"
    s=sf_db(s)
    return s

#########################################################################
def get_video_info(video_id, region='US'):
    # 开发日期：2025-9-28
    # 从EchoTik的实时数据接口realtime，取视频的资料，共28项数据
    url = "https://open.echotik.live/api/v2/rt/video/detail?"
    query = {"video_id": video_id,"region": region}
    zhang_hao=('250915489806340160','3da50707052d408f81cc965d427172cd')  # 用户名和密码
    response = requests.get(url, params=query, auth=zhang_hao)
    data = response.json()
    if data.get('message','')=='success':
        mydata=data['data']                                              # 只要success了，必然会有data
        if mydata:
            return {
                '用户ID': mydata.get('uid', 0),                              # 关于网红的信息，共5项
                '安全用户ID': mydata.get('sec_uid', '0'),
                '用户名': mydata.get('unique_id', 0),
                '昵称': mydata.get('nickname', 0),
                '作者头像': mydata.get('author_avatar', 0),

                '是电商视频': mydata.get('is_ec_video', 0),                  # 关于电商的信息，共4项
                '是广告': mydata.get('is_ads', 0),
                '产品数量': mydata.get('product_cnt', 0),
                '产品ID': mydata.get('product_ids', 0),

                '视频ID': mydata.get('video_id', 0),                         # 关于视频的信息，共7项
                '时长': round(mydata.get('duration', 0) / 1000,0),
                '标题': mydata.get('video_desc', 0),
                '创建时间': datetime.datetime.fromtimestamp(mydata.get('create_time', 0)),
                '视频链接1': mydata.get('play_addr', 0),
                '视频链接2': mydata.get('download_addr', 0),
                '封面URL': mydata.get('cover_url', 0),

                '播放数': mydata.get('play_count', 0),                       # 各项数据，共7项
                '点赞量': mydata.get('digg_count', 0),
                '评论数':mydata.get('comment_count',0),
                '收藏数': mydata.get('collect_count', 0),
                '下载数': mydata.get('download_count', 0),
                '分享数': mydata.get('share_count', 0),
                '转发数': mydata.get('forward_count', 0),

                '描述语言': mydata.get('desc_language', 0),                     # 其他信息，共5项
                '地区': mydata.get('region', 0),
                '字幕': mydata.get('subtitle', []),
                '音乐ID': mydata.get('music_id', 0),
                '音乐标题': mydata.get('music_title', 0)}
    else:
        return {}

#########################################################################
def get_video_info2(网红名,id):
    # 开发日期：2025-09-28
    # 功能：我自己写的函数，给定网红名和视频ID，返回视频的资料，避免用EchoTik的接口
    url=f"https://www.tiktok.com/@{网红名}/video/{id}"
    text=requests.get(url).text
    try:
        标题=text.split('"desc":"')[1].split('"')[0]          # 整理tag词时需要用到标题，因此独立出来
        return {'用户名':网红名,       # text.split('"uniqueId":"')[1].split('"')[0]
                '用户ID':text.split('"author":{"id":"')[1].split('"')[0],
            '用户安全ID':text.split('"secUid":"')[1].split('"')[0],
                  '昵称':text.split('"nickname":"')[1].split('"')[0],
              '创建时间':datetime.datetime.fromtimestamp(int(text.split('"createTime":"')[1].split('"')[0])),
                '播放数':int(text.split('"playCount":"')[1].split('"')[0]),
                '点赞量':int(text.split('"diggCount":"')[1].split('"')[0]),
                '评论数':int(text.split('"commentCount":"')[1].split('"')[0]),
                '收藏数': int(text.split('"collectCount":"')[1].split('"')[0]),
                '分享数':int(text.split('"shareCount":"')[1].split('"')[0]),
                  '时长':int(text.split('"duration":')[1].split(',')[0]),
                  '标题':标题,
                 'tag词':[] if "#" not in 标题 else list(map(lambda x:x.rstrip(),标题.split('#')[1:]))}
    except:
        print('抓取失败，尝试调用EchoTik的rt接口')
        return get_video_info(id)                              # 如果失败，就从EchoTik接口获取


def 启动chrome2():
    import undetected_chromedriver as uc
    driver = uc.Chrome()
    return driver

#########################################################################
# def get_video_info(video_id, region='US', page_num=1, page_size=10):
#     # ========== EchoTik API配置 ==========
#     # BASE_URL_DETAIL = 'https://open.echotik.live/api/v2/video/detail'
#     # BASE_URL_DETAIL = 'https://opendoc.echotik.live/openapi/video/paths/~1rt~1video~1detail/get'
#     BASE_URL_DETAIL =   'https://open.echotik.live/api/v2/rt/video/'
#     # BASE_URL_PRODUCT = 'https://open.echotik.live/api/v2/video/product/list'
#     # =====================================
#     """获取视频完整信息：基础信息 + 关联商品"""
#     headers = {'Authorization': 'Basic MjUwOTE1NDg5ODA2MzQwMTYwOjNkYTUwNzA3MDUyZDQwOGY4MWNjOTY1ZDQyNzE3MmNk'}
#     # 1. 获取视频基础信息
#     detail_params = {
#         'video_ids': video_id,
#         'region': region
#     }
#     detail_response = requests.get(BASE_URL_DETAIL, params=detail_params, headers=headers, timeout=10)
#     detail_data = detail_response.json()
#     video_list = detail_data.get('data', [])
#     info = video_list[0]
#     # 2. 获取视频关联商品
#     product_params = {
#         'video_id': video_id,
#         'region': region,
#         'page_num': page_num,
#         'page_size': page_size
#     }
    # product_response = requests.get(BASE_URL_PRODUCT, params=product_params, headers=headers, timeout=10)
    # products = []
    # if product_response.status_code == 200:
    #     product_data = product_response.json()
    #     if product_data.get('code') == 0:
    #         products_data = product_data.get('data', {})
    #         if isinstance(products_data, dict):
    #             product_list = products_data.get('list', [])
    #         else:
    #             product_list = products_data if isinstance(products_data, list) else []
            # for p in product_list:
            #     products.append({
            #         '商品ID': p.get('product_id', ''),
            #         '商品名称': p.get('product_name', ''),
            #         '价格': p.get('spu_avg_price', 0),
            #         '最小价格': p.get('min_price', 0),
            #         '最大价格': p.get('max_price', 0),
            #         '销量': p.get('total_sale_cnt', 0),
            #         '评分': p.get('product_rating', 0),
            #     })
    # 3. 组合返回结果
    # return {
    #     '视频ID': video_id,
    #     '标题': info.get('video_desc', ''),
    #     '播放量': info.get('total_views_cnt', 0),
    #     '点赞量': info.get('total_digg_cnt', 0),
    #     '评论量': info.get('total_comments_cnt', 0),
    #     '分享量': info.get('total_shares_cnt', 0),
    #     '收藏量': info.get('total_favorites_cnt', 0),
    #     '用户ID': info.get('user_id', ''),
    #     '用户名': info.get('unique_id', ''),
    #     '创建时间': info.get('create_time', ''),
    #     '视频时长': info.get('duration', 0),
    #     '销售标识': info.get('sales_flag', 0),
    #     '视频销售数量': info.get('total_video_sale_cnt', 0),
    #     '视频销售金额': info.get('total_video_sale_gmv_amt', 0),
    #     # '挂载商品': products
    # }

#########################################################################
def 启动Chrome(无头模式=False):
    # 开发日期：2025-09-30
    # 功能：启动Chrome，返回浏览器对象
    options = Options()                                                     # 启动 Chrome，模拟真人
    options.add_argument("--disable-blink-features=AutomationControlled")   # 关闭自动化提示
    # options.add_argument(r"user-data-dir=C:\Users\Administrator\AppData\Local\Google\Chrome\User Data")
    # options.add_argument("profile-directory=Default")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    if 无头模式 == True: options.add_argument('--headless')                  # 无头模式
    options.add_argument('--disable-gpu')                                   # 禁用 GPU（图形处理器）硬件加速
    options.add_argument('--no-sandbox')                                    # 禁用 Chrome 的沙盒安全机制，让浏览器以更高权限运行。
    options.add_argument('--disable-images')                                # 禁用图片加载和显示
    options.add_argument('--disable-javascript')                            # 完全禁用 JavaScript 执行
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2,}) # 2：阻止加载所有图片
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

#########################################################################
def 获取所有文件(文件夹路径):
    # 开发日期：2025-09-30
    # 功能：获取指定目录下的所有文件，将其存储到一个列表中并返回
    文件=[]
    for root,dirs,files in os.walk(文件夹路径):
        for file in files:
            文件.append(os.path.join(root,file))
    return 文件

#########################################################################
def 下载文件(url, 文件名):
    # 开发日期：2025-09-30
    # 功能：给定网络文件路径，将其下载到本地
    try:
        response = requests.get(url)            # 发送 GET 请求下载文件
        if response.status_code == 200:         # 检查请求是否成功
            file_name = url.split('/')[-1]      # 获取文件名（从 URL 中提取）
            with open(文件名, 'wb') as file:     # 将文件保存到本地
                file.write(response.content)
            print(f"文件成功下载到 {文件名}")
            return True
        else:
            print(f"下载失败，HTTP 状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"下载过程中发生错误: {e}")
        return False

#########################################################################
def read_txt(file_path):
    # 2025-10-16：读取txt文件的全部内容
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        return None
    except Exception as e:
        print(f"读取文件时出错：{e}")
        return None

#########################################################################
def 邮箱域名():
    # 2025-10-16：从数据库中获取所有的邮箱域名
    s=获取参数值('邮箱域名')
    return s.split(',')

#########################################################################
def 解析邮箱(描述,所有域名):
    # 2025-10-16：给定达人描述和所有邮箱域名，从达人描述中解析邮箱
    chars= "ABCDEFGHIJKLMNOPQRSTUVWXYZ" \
          +'abcdefghijklmnopqrstuvwxyz' \
          +'0123456789._+-@'                                    # 邮箱中所有可能出现的字符
    YXs=['@'+i for i in 所有域名 if i[0]!='@']                  # 每个邮箱前面加上@
    描述=' '+描述                                               # 描述前面加一个空格，以应对邮箱出现在最前面的情况
    for yx in YXs:
        if yx in 描述:
            for i in range(描述.find(yx),-1,-1):                # 从邮箱后缀出现的位置开始往前查找
                if 描述[i] not in chars:
                    return 描述[i+1:描述.find(yx)+len(yx)]
    return ''

#########################################################################
def 生成linktree(描述):
    # 2025-10-16：给定达人描述，生成linktree
    if 'linktr.ee' in 描述:
        start=描述.find('linktr.ee')
        return 'https://' + 描述[start:]
    else:
        return ''

#########################################################################
def cprint(s,颜色='青'):
    # 2025-10-18：带颜色打印字符串
    c={'红':'\033[0;31m','绿':'\033[0;32m','黄':'\033[0;33m',
       '蓝':'\033[0;34m','紫':'\033[0;35m','青':'\033[0;36m'
       }.get(颜色[0],'\033[0;31m')                    # 如果指定颜色不存在，则默认为红色
    print(f'{c}{s}\033[0m')                           # \033[0m表示恢复默认颜色

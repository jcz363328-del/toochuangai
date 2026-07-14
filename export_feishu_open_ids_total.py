# -*- coding: utf-8 -*-
import json
import os
from datetime import date, datetime, timedelta

import pytds
import requests
from secret_settings import get_feishu_message_config, sql_server_config


_FEISHU_MESSAGE_CONFIG = get_feishu_message_config()
APP_ID = _FEISHU_MESSAGE_CONFIG["app_id"]
APP_SECRET = _FEISHU_MESSAGE_CONFIG["app_secret"]

_DB_CONFIG = sql_server_config()
DB_SERVER = _DB_CONFIG["server"]
DB_DATABASE = _DB_CONFIG["database"]
DB_USER = _DB_CONFIG["user"]
DB_PASSWORD = _DB_CONFIG["password"]
TABLE = "feishu_id"

TOKEN = ""
TOKEN_EXPIRE_AT = datetime.min


def get_token():
    global TOKEN, TOKEN_EXPIRE_AT
    if TOKEN and datetime.now() < TOKEN_EXPIRE_AT:
        return TOKEN
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=20,
    )
    data = r.json() if r.content else {}
    if r.status_code != 200 or int(data.get("code") or 0) != 0:
        raise RuntimeError("获取tenant_access_token失败: " + json.dumps(data, ensure_ascii=False))
    TOKEN = str(data.get("tenant_access_token") or "").strip()
    TOKEN_EXPIRE_AT = datetime.now() + timedelta(seconds=max(60, int(data.get("expire") or 7200) - 60))
    return TOKEN


def feishu_get(session, url, params=None):
    r = session.get(url, headers={"Authorization": f"Bearer {get_token()}"}, params=params or {}, timeout=20)
    data = r.json() if r.content else {}
    if r.status_code != 200 or int(data.get("code") or 0) != 0:
        raise RuntimeError(f"飞书接口失败: {url} {json.dumps(data, ensure_ascii=False)[:800]}")
    return data.get("data") or {}


def list_children(session, department_id, id_type="open_department_id"):
    out, page_token = [], ""
    while True:
        params = {"department_id_type": id_type, "page_size": 50, "fetch_child": False}
        if page_token:
            params["page_token"] = page_token
        data = feishu_get(
            session,
            f"https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children",
            params,
        )
        for item in data.get("items") or []:
            dep_id = str(item.get("open_department_id") or item.get("department_id") or item.get("id") or "").strip()
            if dep_id:
                out.append(dep_id)
        page_token = str(data.get("page_token") or "").strip()
        if not page_token:
            return out


def all_departments(session):
    queue = list_children(session, "0", "department_id")
    seen, out = set(), []
    while queue:
        dep_id = queue.pop(0)
        if not dep_id or dep_id in seen:
            continue
        seen.add(dep_id)
        out.append(dep_id)
        queue.extend([x for x in list_children(session, dep_id) if x not in seen])
    return out


def department_name(session, dep_id, cache):
    if dep_id in cache:
        return cache[dep_id]
    data = feishu_get(
        session,
        f"https://open.feishu.cn/open-apis/contact/v3/departments/{dep_id}",
        {"department_id_type": "open_department_id"},
    )
    name = str((data.get("department") or {}).get("name") or dep_id).strip()
    cache[dep_id] = name
    return name


def list_users(session, dep_id):
    out, page_token = [], ""
    while True:
        params = {
            "department_id_type": "open_department_id",
            "department_id": dep_id,
            "user_id_type": "open_id",
            "page_size": 100,
        }
        if page_token:
            params["page_token"] = page_token
        data = feishu_get(session, "https://open.feishu.cn/open-apis/contact/v3/users", params)
        for item in data.get("items") or []:
            name = str(item.get("name") or "").strip()
            open_id = str(item.get("open_id") or "").strip()
            if name and open_id:
                out.append({"yonghu": name, "feishu_id": open_id})
        page_token = str(data.get("page_token") or "").strip()
        if not page_token:
            return out


def export_rows():
    session = requests.Session()
    deps = all_departments(session)
    if not deps:
        raise RuntimeError("未获取到部门，请检查飞书应用通讯录权限")
    users = {}
    for dep_id in deps:
        for user in list_users(session, dep_id):
            users[user["feishu_id"]] = user
    cache = {}
    rows = sorted(users.values(), key=lambda x: (x["yonghu"], x["feishu_id"]))
    rows += [{"yonghu": department_name(session, dep_id, cache), "feishu_id": dep_id} for dep_id in deps]
    return rows, len(users), len(deps)


def save_rows(rows):
    today = date.today().isoformat()
    conn = pytds.connect(server=DB_SERVER, database=DB_DATABASE, user=DB_USER, password=DB_PASSWORD)
    try:
        cur = conn.cursor()
        cur.execute(f"""
        IF OBJECT_ID(N'dbo.{TABLE}', N'U') IS NULL
            CREATE TABLE dbo.{TABLE} (
                feishu_id NVARCHAR(100) NULL,
                yonghu NVARCHAR(100) NULL,
                quanxian NVARCHAR(200) NULL,
                riqi DATE NULL
            );
        IF COL_LENGTH(N'dbo.{TABLE}', N'quanxian') IS NULL
            ALTER TABLE dbo.{TABLE} ADD quanxian NVARCHAR(200) NULL;
        IF COL_LENGTH(N'dbo.{TABLE}', N'riqi') IS NULL
            ALTER TABLE dbo.{TABLE} ADD riqi DATE NULL;
        """)
        cur.execute(f"DELETE FROM dbo.{TABLE}")
        for row in rows:
            cur.execute(
                f"INSERT INTO dbo.{TABLE} (feishu_id, yonghu, quanxian, riqi) VALUES (%s, %s, %s, %s)",
                (row["feishu_id"], row["yonghu"], "", today),
            )
        if not conn.autocommit:
            conn.commit()
    finally:
        conn.close()


def main():
    print("开始导出飞书通讯录...")
    rows, user_count, dep_count = export_rows()
    save_rows(rows)
    print(json.dumps({
        "success": True,
        "table": TABLE,
        "user_count": user_count,
        "department_count": dep_count,
        "row_count": len(rows),
        "date": date.today().isoformat(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("运行失败:", e)
    if os.name == "nt":
        input("按回车键退出...")

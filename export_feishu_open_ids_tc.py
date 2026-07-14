import json
from datetime import date

import pytds
import requests

from department_permissions import FEISHU_CONFIG, permission_manager
from secret_settings import sql_server_config


_DB_CONFIG = sql_server_config()
DB_SERVER = _DB_CONFIG["server"]
DB_DATABASE = _DB_CONFIG["database"]
DB_USER = _DB_CONFIG["user"]
DB_PASSWORD = _DB_CONFIG["password"]
TARGET_TABLE = "feishu_id_tc"
DEBUG_EXPORT = True


def debug_log(title, payload=None):
    if not DEBUG_EXPORT:
        return
    print(f"[debug] {title}")
    if payload is not None:
        try:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            print(str(payload))


def _preview_text(text, limit=800):
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[:limit] + "...(truncated)"


def get_tenant_access_token():
    token = str(permission_manager.get_access_token() or "").strip()
    if not token:
        raise RuntimeError("未获取到飞书 tenant_access_token")
    return token


def list_department_children(session, token, department_id, department_id_type="open_department_id"):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return []
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    page_token = ""
    out = []
    seen = set()
    for _ in range(50):
        url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{dep_id}/children"
        params = {
            "department_id_type": str(department_id_type or "open_department_id").strip() or "open_department_id",
            "page_size": 50,
            "fetch_child": False,
        }
        if page_token:
            params["page_token"] = page_token
        try:
            resp = session.get(url, headers=headers, params=params, timeout=20)
            data = resp.json() if resp.content else {}
        except Exception as e:
            debug_log("获取子部门接口请求异常", {
                "url": url,
                "department_id": dep_id,
                "department_id_type": department_id_type,
                "page_token": page_token,
                "error": str(e),
            })
            return []
        if resp.status_code != 200 or int(data.get("code") or 0) != 0:
            debug_log("获取子部门接口返回失败", {
                "url": url,
                "department_id": dep_id,
                "department_id_type": department_id_type,
                "page_token": page_token,
                "status_code": resp.status_code,
                "code": data.get("code"),
                "msg": data.get("msg"),
                "response_preview": _preview_text(resp.text),
            })
            return []
        items = ((data.get("data") or {}).get("items") or [])
        for item in items:
            one_id = str(
                (item or {}).get("open_department_id")
                or (item or {}).get("department_id")
                or (item or {}).get("id")
                or ""
            ).strip()
            if one_id and one_id not in seen:
                seen.add(one_id)
                out.append(one_id)
        page_token = str(((data.get("data") or {}).get("page_token") or "")).strip()
        if not page_token:
            break
    return out


def get_root_departments(session, token):
    roots = list_department_children(session, token, "0", department_id_type="department_id")
    debug_log("实时根部门结果", {
        "count": len(roots or []),
        "items_preview": (roots or [])[:20],
    })
    return sorted({str(x).strip() for x in (roots or []) if str(x).strip()})


def expand_all_departments(session, token):
    queue = list(get_root_departments(session, token))
    out = []
    seen = set()
    while queue:
        current = str(queue.pop(0) or "").strip()
        if not current or current in seen:
            continue
        seen.add(current)
        out.append(current)
        for child_id in list_department_children(session, token, current):
            if child_id and child_id not in seen:
                queue.append(child_id)
    return out


def list_users_by_department(session, token, department_id):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return []
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    page_token = ""
    out = []
    for _ in range(50):
        url = "https://open.feishu.cn/open-apis/contact/v3/users"
        params = {
            "department_id_type": "open_department_id",
            "department_id": dep_id,
            "user_id_type": "open_id",
            "page_size": 100,
        }
        if page_token:
            params["page_token"] = page_token
        try:
            resp = session.get(url, headers=headers, params=params, timeout=20)
            data = resp.json() if resp.content else {}
        except Exception as e:
            debug_log("获取部门用户接口请求异常", {
                "url": url,
                "department_id": dep_id,
                "page_token": page_token,
                "error": str(e),
            })
            break
        if resp.status_code != 200 or int(data.get("code") or 0) != 0:
            debug_log("获取部门用户接口返回失败", {
                "url": url,
                "department_id": dep_id,
                "page_token": page_token,
                "status_code": resp.status_code,
                "code": data.get("code"),
                "msg": data.get("msg"),
                "response_preview": _preview_text(resp.text),
            })
            break
        items = ((data.get("data") or {}).get("items") or [])
        for item in items:
            open_id = str((item or {}).get("open_id") or "").strip()
            name = str((item or {}).get("name") or "").strip()
            department_ids = []
            raw_department_ids = (item or {}).get("department_ids") or []
            if isinstance(raw_department_ids, list):
                department_ids.extend([str(x or "").strip() for x in raw_department_ids if str(x or "").strip()])
            if dep_id and dep_id not in department_ids:
                department_ids.append(dep_id)
            if open_id and name:
                out.append({
                    "yonghu": name,
                    "feishu_id": open_id,
                    "department_ids": department_ids,
                })
        page_token = str(((data.get("data") or {}).get("page_token") or "")).strip()
        if not page_token:
            break
    return out


def get_department_name(session, token, department_id, cache=None):
    dep_id = str(department_id or "").strip()
    if not dep_id:
        return ""
    cache = cache if isinstance(cache, dict) else {}
    if dep_id in cache:
        return str(cache.get(dep_id) or "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    try:
        url = f"https://open.feishu.cn/open-apis/contact/v3/departments/{dep_id}"
        params = {
            "department_id_type": "open_department_id",
        }
        resp = session.get(url, headers=headers, params=params, timeout=20)
        data = resp.json() if resp.content else {}
        if resp.status_code == 200 and int(data.get("code") or 0) == 0:
            info = (data.get("data") or {}).get("department") or {}
            name = str(info.get("name") or "").strip()
            if name:
                cache[dep_id] = name
                return name
        debug_log("获取部门名称接口返回失败", {
            "url": url,
            "department_id": dep_id,
            "status_code": resp.status_code,
            "code": data.get("code"),
            "msg": data.get("msg"),
            "response_preview": _preview_text(resp.text),
        })
    except Exception as e:
        debug_log("获取部门名称接口请求异常", {
            "department_id": dep_id,
            "error": str(e),
        })
    cache[dep_id] = dep_id
    return dep_id


def export_all_users():
    token = get_tenant_access_token()
    debug_log("tenant_access_token 获取成功", {
        "app_id": FEISHU_CONFIG.get("app_id"),
        "token_prefix": token[:18] + "..." if token else "",
    })
    session = requests.Session()
    root_departments = get_root_departments(session, token)
    if not root_departments:
        debug_log("根部门为空，停止导出", {
            "reason": "未从飞书通讯录实时获取到根部门",
            "hint": "请检查应用通讯录权限范围，或查看上方 departments children 接口返回的 code/msg",
        })
        raise RuntimeError("未从飞书通讯录实时获取到根部门，请检查应用通讯录权限范围")
    all_departments = expand_all_departments(session, token)
    if not all_departments:
        raise RuntimeError("未获取到任何部门，请检查通讯录权限或部门范围")
    debug_log("部门树展开完成", {
        "root_department_count": len(root_departments),
        "department_count": len(all_departments),
        "department_preview": all_departments[:30],
    })

    user_map = {}
    for dep_id in all_departments:
        users = list_users_by_department(session, token, dep_id)
        for user in users:
            open_id = str(user.get("feishu_id") or "").strip()
            name = str(user.get("yonghu") or "").strip()
            department_ids = [str(x or "").strip() for x in (user.get("department_ids") or []) if str(x or "").strip()]
            if not open_id or not name:
                continue
            existing = user_map.get(open_id) or {"yonghu": name, "feishu_id": open_id, "department_ids": []}
            existing["yonghu"] = name
            existing["feishu_id"] = open_id
            existing_ids = [str(x or "").strip() for x in (existing.get("department_ids") or []) if str(x or "").strip()]
            merged_ids = sorted(set(existing_ids + department_ids))
            existing["department_ids"] = merged_ids
            user_map[open_id] = existing

    user_rows = sorted(user_map.values(), key=lambda x: (str(x.get("yonghu") or ""), str(x.get("feishu_id") or "")))
    if not user_rows:
        raise RuntimeError("未导出到任何用户，请检查应用通讯录权限")
    department_name_cache = {}
    department_rows = []
    for dep_id in sorted({str(x or "").strip() for x in all_departments if str(x or "").strip()}):
        department_rows.append({
            "yonghu": get_department_name(session, token, dep_id, department_name_cache),
            "feishu_id": dep_id,
        })
    rows = []
    rows.extend([{"yonghu": str(x.get("yonghu") or "").strip(), "feishu_id": str(x.get("feishu_id") or "").strip()} for x in user_rows])
    rows.extend([{"yonghu": str(x.get("yonghu") or "").strip(), "feishu_id": str(x.get("feishu_id") or "").strip()} for x in department_rows])
    return {
        "root_department_count": len(root_departments),
        "department_count": len(all_departments),
        "user_count": len(user_rows),
        "department_row_count": len(department_rows),
        "row_count": len(rows),
        "rows": rows,
    }


def ensure_table(cursor):
    cursor.execute(
        f"""
        IF OBJECT_ID(N'dbo.{TARGET_TABLE}', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.{TARGET_TABLE} (
                yonghu NVARCHAR(100) NOT NULL,
                feishu_id NVARCHAR(100) NOT NULL,
                riqi DATE NOT NULL
            );
        END
        """
    )


def replace_table_rows(users):
    today = date.today().isoformat()
    conn = pytds.connect(
        server=DB_SERVER,
        database=DB_DATABASE,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    try:
        cursor = conn.cursor()
        ensure_table(cursor)
        cursor.execute(f"DELETE FROM dbo.{TARGET_TABLE}")
        for user in users:
            cursor.execute(
                f"INSERT INTO dbo.{TARGET_TABLE} (yonghu, feishu_id, riqi) VALUES (%s, %s, %s)",
                (str(user.get("yonghu") or "").strip(), str(user.get("feishu_id") or "").strip(), today),
            )
        if not conn.autocommit:
            conn.commit()
    finally:
        conn.close()


def main():
    print(f"开始导出飞书通讯录，应用 app_id: {FEISHU_CONFIG.get('app_id')}")
    payload = export_all_users()
    replace_table_rows(payload["rows"])
    print(
        json.dumps(
            {
                "success": True,
                "app_id": FEISHU_CONFIG.get("app_id"),
                "root_department_count": payload["root_department_count"],
                "department_count": payload["department_count"],
                "user_count": payload["user_count"],
                "department_row_count": payload["department_row_count"],
                "row_count": payload["row_count"],
                "table": TARGET_TABLE,
                "yonghu_format": "用户名或部门名",
                "import_date": date.today().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""将飞书通讯录部门组织架构完整同步到 dbo.FeiShu_JiaGou。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytds
import requests

from secret_settings import get_feishu_config, sql_server_config


TABLE_NAME = "FeiShu_JiaGou"
MIGRATION_PATH = Path(__file__).resolve().parent / "migrations" / "20260718_feishu_jiagou.sql"


def _required_config(config: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    missing = [key for key in keys if not config.get(key)]
    if missing:
        raise RuntimeError(f"{label}配置缺少: {', '.join(missing)}")


def _get_tenant_access_token(session: requests.Session) -> str:
    config = get_feishu_config()
    _required_config(config, ("app_id", "app_secret"), "飞书")
    response = session.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": config["app_id"], "app_secret": config["app_secret"]},
        timeout=20,
    )
    data = response.json() if response.content else {}
    if response.status_code != 200 or int(data.get("code") or 0) != 0:
        raise RuntimeError(f"获取飞书访问凭证失败: {data.get('msg') or response.status_code}")
    token = str(data.get("tenant_access_token") or "").strip()
    if not token:
        raise RuntimeError("飞书接口未返回访问凭证")
    return token


def _feishu_get(
    session: requests.Session,
    token: str,
    url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = session.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=20,
    )
    data = response.json() if response.content else {}
    if response.status_code != 200 or int(data.get("code") or 0) != 0:
        error_message = str(data.get("msg") or data.get("message") or response.status_code)
        raise RuntimeError(f"读取飞书通讯录失败: {error_message}")
    return data.get("data") or {}


def _list_department_children(
    session: requests.Session,
    token: str,
    parent_department_id: str,
    department_id_type: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {
            "department_id_type": department_id_type,
            "user_id_type": "open_id",
            "page_size": 50,
            "fetch_child": False,
        }
        if page_token:
            params["page_token"] = page_token
        data = _feishu_get(
            session,
            token,
            f"https://open.feishu.cn/open-apis/contact/v3/departments/{parent_department_id}/children",
            params,
        )
        items.extend(item for item in (data.get("items") or []) if isinstance(item, dict))
        page_token = str(data.get("page_token") or "").strip()
        if not page_token:
            return items


def _list_department_users(
    session: requests.Session,
    token: str,
    department_id: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {
            "department_id_type": "open_department_id",
            "department_id": department_id,
            "user_id_type": "open_id",
            "page_size": 100,
        }
        if page_token:
            params["page_token"] = page_token
        data = _feishu_get(
            session,
            token,
            "https://open.feishu.cn/open-apis/contact/v3/users",
            params,
        )
        items.extend(item for item in (data.get("items") or []) if isinstance(item, dict))
        page_token = str(data.get("page_token") or "").strip()
        if not page_token:
            break

    users_by_open_id: dict[str, dict[str, Any]] = {}
    for item in items:
        open_id = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not open_id or not name:
            continue
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        users_by_open_id[open_id] = {
            "姓名": name,
            "飞书用户OpenId": open_id,
            "飞书内部用户Id": str(item.get("user_id") or "").strip() or None,
            "工号": str(item.get("employee_no") or "").strip() or None,
            "职位": str(item.get("job_title") or "").strip() or None,
            "是否离职": bool(status.get("is_resigned")),
        }
    return sorted(
        users_by_open_id.values(),
        key=lambda user: (str(user["姓名"]), str(user["飞书用户OpenId"])),
    )


def _get_application_name(session: requests.Session, token: str) -> str:
    response = session.get(
        "https://open.feishu.cn/open-apis/bot/v3/info",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    data = response.json() if response.content else {}
    if response.status_code != 200 or int(data.get("code") or 0) != 0:
        return "未知应用"
    bot = data.get("bot") or (data.get("data") or {}).get("bot") or data.get("data") or {}
    return str(bot.get("app_name") or bot.get("name") or "未知应用").strip()


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def fetch_feishu_department_rows() -> tuple[list[dict[str, Any]], str, str]:
    session = requests.Session()
    config = get_feishu_config()
    token = _get_tenant_access_token(session)
    app_id = str(config.get("app_id") or "").strip()
    app_name = _get_application_name(session, token)
    queue: list[tuple[str, str, int, list[str]]] = [("0", "department_id", 0, [])]
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    while queue:
        parent_id, parent_id_type, parent_level, parent_path = queue.pop(0)
        children = _list_department_children(session, token, parent_id, parent_id_type)
        for item in children:
            open_department_id = str(
                item.get("open_department_id")
                or item.get("department_id")
                or item.get("id")
                or ""
            ).strip()
            if not open_department_id or open_department_id in seen:
                continue
            seen.add(open_department_id)

            department_name = str(item.get("name") or open_department_id).strip()
            level = parent_level + 1
            path_parts = [*parent_path, department_name]
            status = item.get("status") if isinstance(item.get("status"), dict) else {}
            unit_ids = item.get("unit_ids") if isinstance(item.get("unit_ids"), list) else []

            rows.append({
                "FeiShuBuMenId": open_department_id,
                "FeiShuNeiBuBuMenId": str(item.get("department_id") or "").strip() or None,
                "BuMenMingCheng": department_name,
                "FuJiBuMenId": parent_id,
                "FuJiBuMenMingCheng": "企业根组织" if parent_id == "0" else None,
                "BuMenLuJing": " / ".join(path_parts),
                "CengJi": level,
                "PaiXu": _to_int(item.get("order")),
                "FuZeRenYongHuId": str(item.get("leader_user_id") or "").strip() or None,
                "BuMenQunLiaoId": str(item.get("chat_id") or "").strip() or None,
                "ChengYuanShuLiang": _to_int(item.get("member_count")),
                "DanWeiIdLieBiao": json.dumps(unit_ids, ensure_ascii=False),
                "ShiFouYouZiBuMen": False,
                "ShiFouYiShanChu": bool(status.get("is_deleted")),
                "YuanShiShuJu": json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            })
            queue.append((open_department_id, "open_department_id", level, path_parts))

    if not rows:
        raise RuntimeError("未读取到任何飞书部门，请检查应用通讯录权限范围")

    name_by_id = {row["FeiShuBuMenId"]: row["BuMenMingCheng"] for row in rows}
    parent_ids = {row["FuJiBuMenId"] for row in rows if row["FuJiBuMenId"] != "0"}
    for row in rows:
        if row["FuJiBuMenId"] != "0":
            row["FuJiBuMenMingCheng"] = name_by_id.get(row["FuJiBuMenId"])
        row["ShiFouYouZiBuMen"] = row["FeiShuBuMenId"] in parent_ids
        users = _list_department_users(session, token, row["FeiShuBuMenId"])
        row["ChengYuanShuLiang"] = len(users)
        row["BuMenRenYuanMingCheng"] = "、".join(str(user["姓名"]) for user in users)
        row["BuMenRenYuanXinXi"] = json.dumps(users, ensure_ascii=False, separators=(",", ":"))

    return (
        sorted(rows, key=lambda row: (row["CengJi"], row["BuMenLuJing"], row["FeiShuBuMenId"])),
        app_name,
        app_id,
    )


def save_department_rows(rows: list[dict[str, Any]], app_name: str, app_id: str) -> None:
    database_config = sql_server_config()
    _required_config(database_config, ("server", "database", "user", "password"), "数据库")
    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
    sync_time = datetime.now().replace(microsecond=0)
    connection = pytds.connect(**database_config)
    try:
        cursor = connection.cursor()
        cursor.execute(migration_sql)
        cursor.execute(f"DELETE FROM dbo.{TABLE_NAME}")
        cursor.executemany(
            f"""
            INSERT INTO dbo.{TABLE_NAME} (
                FeiShuBuMenId,
                FeiShuNeiBuBuMenId,
                BuMenMingCheng,
                FuJiBuMenId,
                FuJiBuMenMingCheng,
                BuMenLuJing,
                CengJi,
                PaiXu,
                FuZeRenYongHuId,
                BuMenQunLiaoId,
                ChengYuanShuLiang,
                BuMenRenYuanMingCheng,
                BuMenRenYuanXinXi,
                DanWeiIdLieBiao,
                ShiFouYouZiBuMen,
                ShiFouYiShanChu,
                TongBuShiJian,
                YuanShiShuJu
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["FeiShuBuMenId"],
                    row["FeiShuNeiBuBuMenId"],
                    row["BuMenMingCheng"],
                    row["FuJiBuMenId"],
                    row["FuJiBuMenMingCheng"],
                    row["BuMenLuJing"],
                    row["CengJi"],
                    row["PaiXu"],
                    row["FuZeRenYongHuId"],
                    row["BuMenQunLiaoId"],
                    row["ChengYuanShuLiang"],
                    row["BuMenRenYuanMingCheng"],
                    row["BuMenRenYuanXinXi"],
                    row["DanWeiIdLieBiao"],
                    row["ShiFouYouZiBuMen"],
                    row["ShiFouYiShanChu"],
                    sync_time,
                    row["YuanShiShuJu"],
                )
                for row in rows
            ],
        )
        table_description = (
            f"飞书通讯录部门组织架构，每行代表一个部门；"
            f"数据来源企业自建应用：{app_name}（App ID：{app_id}）"
        )
        cursor.execute(
            """
            DECLARE @TableDescription NVARCHAR(4000) = %s;
            EXEC sys.sp_updateextendedproperty
                @name=N'MS_Description', @value=@TableDescription,
                @level0type=N'SCHEMA', @level0name=N'dbo',
                @level1type=N'TABLE', @level1name=N'FeiShu_JiaGou'
            """,
            (table_description,),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="同步飞书通讯录部门组织架构")
    parser.add_argument("--apply", action="store_true", help="实际写入 SQL Server；默认仅拉取并检查")
    args = parser.parse_args()

    rows, app_name, app_id = fetch_feishu_department_rows()
    max_level = max(row["CengJi"] for row in rows)
    top_level_count = sum(1 for row in rows if row["FuJiBuMenId"] == "0")
    if args.apply:
        save_department_rows(rows, app_name, app_id)

    print(json.dumps({
        "success": True,
        "mode": "applied" if args.apply else "dry-run",
        "table": f"dbo.{TABLE_NAME}",
        "source_application": app_name,
        "source_application_app_id": app_id,
        "department_count": len(rows),
        "department_member_count": sum(row["ChengYuanShuLiang"] for row in rows),
        "top_level_count": top_level_count,
        "max_level": max_level,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

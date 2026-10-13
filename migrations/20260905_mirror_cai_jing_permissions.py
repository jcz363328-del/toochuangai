"""Mirror Zhou Juncheng's named permissions to Cai Jing without replacing admin edits."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


SOURCE_USER = "周俊成"
TARGET_USER = "蔡晶"


def split_permission_users(value):
    return [
        item.strip()
        for item in re.split(r"[；;,，、\r\n]+", str(value or ""))
        if item.strip()
    ]


def mirrored_permission_users(value):
    original = str(value or "").strip()
    users = split_permission_users(original)
    if SOURCE_USER not in users or TARGET_USER in users:
        return original
    return f"{original}；{TARGET_USER}" if original else TARGET_USER


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    updated_functions = []
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT ID, GongNeng, YongHu FROM dbo.quanxian ORDER BY ID")
        for row_id, function_name, users in cursor.fetchall() or []:
            mirrored_users = mirrored_permission_users(users)
            if mirrored_users == str(users or "").strip():
                continue
            cursor.execute(
                """
                UPDATE dbo.quanxian
                SET YongHu=%s, GengXinShiJian=SYSDATETIME()
                WHERE ID=%s
                """,
                (mirrored_users, row_id),
            )
            updated_functions.append(str(function_name or "").strip())
        if not connection.autocommit:
            connection.commit()
        return updated_functions
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    updated = apply_migration()
    print(f"mirrored_permissions={len(updated)}")
    for function_name in updated:
        print(function_name)

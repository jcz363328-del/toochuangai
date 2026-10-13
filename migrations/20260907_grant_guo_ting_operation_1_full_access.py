"""Grant Guo Ting complete operation-department-1 access without cross-department scope."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


TARGET_USER = "郭婷"
TARGET_FUNCTIONS = (
    "operation_dept_1",
    "review_analysis",
    "amazon_reply_agent",
    "operation_fba_shipping",
    "tk_dashboard_90",
    "business_analysis",
)


def split_permission_users(value):
    return [
        item.strip()
        for item in re.split(r"[；;,，、\r\n]+", str(value or ""))
        if item.strip()
    ]


def add_target_user(value):
    original = str(value or "").strip()
    if TARGET_USER in split_permission_users(original):
        return original
    return f"{original}；{TARGET_USER}" if original else TARGET_USER


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    updated_functions = []
    try:
        cursor = connection.cursor()
        placeholders = ", ".join(["%s"] * len(TARGET_FUNCTIONS))
        cursor.execute(
            f"""
            SELECT ID, GongNeng, YongHu
            FROM dbo.quanxian
            WHERE LTRIM(RTRIM(GongNeng)) IN ({placeholders})
            ORDER BY GongNeng
            """,
            TARGET_FUNCTIONS,
        )
        rows = cursor.fetchall() or []
        found_functions = {str(row[1] or "").strip() for row in rows}
        missing_functions = sorted(set(TARGET_FUNCTIONS) - found_functions)
        if missing_functions:
            raise RuntimeError(
                "Missing permission rows: " + ", ".join(missing_functions)
            )

        for row_id, function_name, users in rows:
            updated_users = add_target_user(users)
            if updated_users == str(users or "").strip():
                continue
            cursor.execute(
                """
                UPDATE dbo.quanxian
                SET YongHu=%s, GengXinShiJian=SYSDATETIME()
                WHERE ID=%s
                """,
                (updated_users, row_id),
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
    print(f"granted_permissions={len(updated)}")
    for function_name in updated:
        print(function_name)

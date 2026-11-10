"""Grant Ren Zhenmin business-analysis entry and full-data permissions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


USER_NAME = "任真民"
PERMISSIONS = ("business_analysis", "business_analysis_all")


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE dbo.quanxian
            SET YongHu = CASE
                    WHEN CHARINDEX(%s, ISNULL(YongHu, N'')) > 0 THEN YongHu
                    WHEN LTRIM(RTRIM(ISNULL(YongHu, N''))) = N'' THEN %s
                    ELSE RTRIM(YongHu) + N'；' + %s
                END,
                QiYong = 1,
                GengXinShiJian = SYSDATETIME()
            WHERE LTRIM(RTRIM(GongNeng)) IN (%s, %s)
            """,
            (USER_NAME, USER_NAME, USER_NAME, *PERMISSIONS),
        )
        if not connection.autocommit:
            connection.commit()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


def verify_permissions():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT GongNeng, YongHu, QiYong FROM dbo.quanxian "
            "WHERE LTRIM(RTRIM(GongNeng)) IN (%s, %s)",
            PERMISSIONS,
        )
        rows = {
            str(row[0] or "").strip(): {
                "users": str(row[1] or ""),
                "enabled": bool(row[2]),
            }
            for row in cursor.fetchall()
        }
        return {
            name: rows.get(name, {}).get("enabled", False)
            and USER_NAME in rows.get(name, {}).get("users", "")
            for name in PERMISSIONS
        }
    finally:
        connection.close()


if __name__ == "__main__":
    apply_migration()
    print(verify_permissions())

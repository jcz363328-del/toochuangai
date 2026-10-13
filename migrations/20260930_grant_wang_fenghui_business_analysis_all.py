"""Grant Wang Fenghui the same business-analysis permissions as Zhou Juncheng."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


SQL = """
UPDATE dbo.quanxian
SET YongHu = CASE
        WHEN CHARINDEX(N'王丰慧', ISNULL(YongHu, N'')) > 0 THEN YongHu
        WHEN LTRIM(RTRIM(ISNULL(YongHu, N''))) = N'' THEN N'王丰慧'
        ELSE RTRIM(YongHu) + N'；王丰慧'
    END,
    QiYong = 1,
    GengXinShiJian = SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng)) IN (N'business_analysis', N'business_analysis_all')
  AND CHARINDEX(N'周俊成', ISNULL(YongHu, N'')) > 0;
"""


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(SQL)
        if not connection.autocommit:
            connection.commit()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


def verify_permission():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT YongHu FROM dbo.quanxian "
            "WHERE LTRIM(RTRIM(GongNeng)) = N'business_analysis_all'"
        )
        row = cursor.fetchone()
        users = str(row[0] or "") if row else ""
        return "周俊成" in users and "王丰慧" in users
    finally:
        connection.close()


if __name__ == "__main__":
    apply_migration()
    print(f"wang_fenghui_business_analysis_all_verified={verify_permission()}")

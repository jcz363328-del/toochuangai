"""Grant Li Baoju business-analysis entry and full-data permissions."""

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
        WHEN CHARINDEX(N'李宝菊', ISNULL(YongHu, N'')) > 0 THEN YongHu
        WHEN LTRIM(RTRIM(ISNULL(YongHu, N''))) = N'' THEN N'李宝菊'
        ELSE RTRIM(YongHu) + N'；李宝菊'
    END,
    QiYong = 1,
    GengXinShiJian = SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng)) IN (N'business_analysis', N'business_analysis_all');
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


def verify_permissions():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT GongNeng, YongHu FROM dbo.quanxian "
            "WHERE LTRIM(RTRIM(GongNeng)) IN (N'business_analysis', N'business_analysis_all')"
        )
        rows = {str(row[0] or '').strip(): str(row[1] or '') for row in cursor.fetchall()}
        return {
            name: ('李宝菊' in rows.get(name, ''))
            for name in ('business_analysis', 'business_analysis_all')
        }
    finally:
        connection.close()


if __name__ == "__main__":
    apply_migration()
    print(verify_permissions())

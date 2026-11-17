"""Grant Zhou Juncheng access to the TikTok replenishment center."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


PERMISSION_NAME = "daily_replenishment_tiktok"
USER_NAME = "周俊成"


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE dbo.quanxian
               SET YongHu = CASE
                   WHEN CHARINDEX(N'周俊成', ISNULL(YongHu, N'')) > 0 THEN YongHu
                   WHEN NULLIF(LTRIM(RTRIM(ISNULL(YongHu, N''))), N'') IS NULL THEN N'周俊成'
                   ELSE LTRIM(RTRIM(YongHu)) + N'；周俊成'
               END,
                   QiYong = 1,
                   GengXinShiJian = SYSDATETIME()
             WHERE LTRIM(RTRIM(GongNeng)) = %s
            """,
            (PERMISSION_NAME,),
        )
        if cursor.rowcount == 0:
            raise RuntimeError(f"Permission row does not exist: {PERMISSION_NAME}")
        if not connection.autocommit:
            connection.commit()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    apply_migration()
    print("daily_replenishment_tiktok_zhou_juncheng=granted")

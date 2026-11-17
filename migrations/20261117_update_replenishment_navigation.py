"""Rename the Amazon replenishment center and move TikTok under the content factory."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE dbo.quanxian
               SET MingCheng=N'智能补货中心-亚马逊',
                   MiaoShu=REPLACE(MiaoShu,N'智能补货中心-运营',N'智能补货中心-亚马逊'),
                   GengXinShiJian=SYSDATETIME()
             WHERE LTRIM(RTRIM(GongNeng))=N'daily_replenishment_operation'
            """
        )
        if cursor.rowcount == 0:
            raise RuntimeError("Permission row does not exist: daily_replenishment_operation")
        cursor.execute(
            """
            UPDATE dbo.quanxian
               SET FuJiGongNeng=N'tk_project_group',
                   GengXinShiJian=SYSDATETIME()
             WHERE LTRIM(RTRIM(GongNeng))=N'daily_replenishment_tiktok'
            """
        )
        if cursor.rowcount == 0:
            raise RuntimeError("Permission row does not exist: daily_replenishment_tiktok")
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
    print("replenishment_navigation=updated")

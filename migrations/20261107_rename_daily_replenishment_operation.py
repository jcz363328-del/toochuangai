"""Rename the daily replenishment operation permission to 智能补货中心-运营."""

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
               SET MingCheng=N'智能补货中心-运营',
                   GengXinShiJian=SYSDATETIME()
             WHERE LTRIM(RTRIM(GongNeng))=N'daily_replenishment_operation'
            """
        )
        if cursor.rowcount == 0:
            raise RuntimeError("Permission row does not exist: daily_replenishment_operation")
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
    print("daily_replenishment_operation_name=renamed")

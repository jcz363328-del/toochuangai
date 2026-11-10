"""Correct the FBA shipping grantee from 曹圆圆 to 曹园园."""

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
               SET YongHu=N'郭婷；曹园园',
                   QiYong=1,
                   GengXinShiJian=SYSDATETIME()
             WHERE LTRIM(RTRIM(GongNeng))=N'operation_fba_shipping'
            """
        )
        if cursor.rowcount == 0:
            raise RuntimeError("Permission row does not exist: operation_fba_shipping")
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
    print("cao_yuanyuan_fba_shipping_name=corrected")

"""Grant Cao Yuanyuan (曹园园) access to FBA shipping methods."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


PERMISSION_KEY = "operation_fba_shipping"
TARGET_USER = "曹园园"


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE dbo.quanxian
               SET YongHu = CASE
                   WHEN NULLIF(LTRIM(RTRIM(ISNULL(YongHu, ''))), '') IS NULL THEN %s
                   WHEN N'；' + REPLACE(REPLACE(YongHu, N';', N'；'), N' ', N'') + N'；'
                        LIKE N'%%；' + %s + N'；%%' THEN YongHu
                   ELSE RTRIM(YongHu) + N'；' + %s
               END,
                   QiYong=1,
                   GengXinShiJian=SYSDATETIME()
             WHERE LTRIM(RTRIM(GongNeng))=%s
            """,
            (TARGET_USER, TARGET_USER, TARGET_USER, PERMISSION_KEY),
        )
        if cursor.rowcount == 0:
            raise RuntimeError(f"Permission row does not exist: {PERMISSION_KEY}")
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
    print("cao_yuanyuan_fba_shipping_permission=ready")

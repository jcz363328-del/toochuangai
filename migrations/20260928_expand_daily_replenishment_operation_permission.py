"""Allow operations departments to use their store-scoped replenishment workbook."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


UPDATE_SQL = """
UPDATE dbo.quanxian
SET BuMen=N'运营部；AI部；总经办',
    FuJiGongNeng=N'',
    MiaoShu=N'运营人员按飞书用户名匹配 v_PinPaiDianPu.YunYing，仅查看本人负责店铺。',
    QiYong=1,
    GengXinShiJian=SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng))=N'daily_replenishment_operation';
"""


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(UPDATE_SQL, None)
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
    print("daily_replenishment_operation_permission=expanded")

"""Add the independent daily replenishment operation feature permission."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


PERMISSION_ROW = {
    "gongneng": "daily_replenishment_operation",
    "yonghu": "",
    "bumen": "AI部",
    "fujigongneng": "ai_dept",
    "mingcheng": "日常补货运营",
    "miaoshu": "独立的日常补货运营版多工作表刷新功能，仅允许 AI部访问。",
}

UPSERT_SQL = """
UPDATE dbo.quanxian
SET YongHu=%s, BuMen=%s, FuJiGongNeng=%s, MingCheng=%s, MiaoShu=%s,
    QiYong=1, GengXinShiJian=SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng))=%s;
IF @@ROWCOUNT=0
BEGIN
    INSERT INTO dbo.quanxian
        (GongNeng,YongHu,BuMen,FuJiGongNeng,MingCheng,MiaoShu,QiYong,GengXinShiJian)
    VALUES (%s,%s,%s,%s,%s,%s,1,SYSDATETIME());
END;
"""


def apply_migration():
    row = PERMISSION_ROW
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            UPSERT_SQL,
            (
                row["yonghu"], row["bumen"], row["fujigongneng"], row["mingcheng"],
                row["miaoshu"], row["gongneng"], row["gongneng"], row["yonghu"],
                row["bumen"], row["fujigongneng"], row["mingcheng"], row["miaoshu"],
            ),
        )
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
    print("daily_replenishment_operation_permission=applied")

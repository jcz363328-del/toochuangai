"""Add the scoped MAGIC AD permission to dbo.quanxian."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


PERMISSION_ROW = {
    "gongneng": "ads_monitor",
    "yonghu": "孙洁；侯梁",
    "bumen": "AI部；总经办",
    "fujigongneng": "ai_dept",
    "mingcheng": "MAGIC AD 广告监控",
    "miaoshu": "MAGIC AD 广告监控页面、静态资源与诊断接口权限。",
}


UPSERT_SQL = """
UPDATE dbo.quanxian
SET YongHu=%s,
    BuMen=%s,
    FuJiGongNeng=%s,
    MingCheng=%s,
    MiaoShu=%s,
    QiYong=1,
    GengXinShiJian=SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng))=%s;

IF @@ROWCOUNT=0
BEGIN
    INSERT INTO dbo.quanxian
        (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
    VALUES
        (%s, %s, %s, %s, %s, %s, 1, SYSDATETIME());
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
                row["yonghu"],
                row["bumen"],
                row["fujigongneng"],
                row["mingcheng"],
                row["miaoshu"],
                row["gongneng"],
                row["gongneng"],
                row["yonghu"],
                row["bumen"],
                row["fujigongneng"],
                row["mingcheng"],
                row["miaoshu"],
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
    print("ads_monitor_permission=applied")

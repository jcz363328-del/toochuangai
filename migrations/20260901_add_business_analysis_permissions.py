"""Add the formal business-analysis permissions to dbo.quanxian."""

from __future__ import annotations

import pytds

from secret_settings import sql_server_config


PERMISSION_ROWS = (
    {
        "gongneng": "business_analysis",
        "yonghu": "",
        "bumen": "运营一部；运营二部；运营三部；运营六部；运营七部；AI部；总经办",
        "fujigongneng": "ai_dept",
        "mingcheng": "经营分析",
        "miaoshu": "经营分析入口权限；部门负责人仅看本部门，普通员工仅看本人，未命中全量权限时仅展示比例数据。",
    },
    {
        "gongneng": "business_analysis_all",
        "yonghu": "周俊成；侯梁；孙洁；刘蓉蓉",
        "bumen": "AI部；总经办",
        "fujigongneng": "business_analysis",
        "mingcheng": "经营分析（全量权限）",
        "miaoshu": "经营分析全量数据与全部关键任务管理权限。",
    },
)


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
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        for row in PERMISSION_ROWS:
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
    print("business_analysis_permissions=applied")
